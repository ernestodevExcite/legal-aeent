"""
Ruta: Ingesta de documentos
POST /ingest/upload
"""

import os
import json
import shutil
import logging
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlmodel import Session, select

from config import settings
from database import get_session
from models import Contract, ActivityLog
from services.document_processor import extract_text, chunk_text, extract_metadata_heuristic
from services.rag_service import index_contract
from services.llm_service import summarize_contract, analyze_clauses
from routes.auth import get_current_user


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("API -docs")

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


@router.post("/upload")
async def upload_contract(
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Carga, procesa e indexa un contrato."""

    # Validar extensión
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Formato no soportado. Use: {ALLOWED_EXTENSIONS}")

    # Guardar archivo
    raw_dir = Path(settings.data_dir) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_name = f"{timestamp}_{file.filename}"
    filepath = str(raw_dir / safe_name)

    with open(filepath, "wb") as f:
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(400, "Archivo demasiado grande (máx 50MB)")
        f.write(content)

    try:
        # Extraer texto
        text = extract_text(filepath)
        if not text or len(text.strip()) < 50:
            raise HTTPException(422, "No se pudo extraer texto del documento")

        # Extraer metadatos heurísticos
        metadata = extract_metadata_heuristic(text)

        # Generar resumen y análisis de cláusulas
        summary = summarize_contract(text)
        clauses_result = analyze_clauses(text)

        # Determinar nivel de riesgo
        risk_level = clauses_result.get("overall_risk", "unknown")

        # Guardar contrato en BD
        contract = Contract(
            filename=file.filename,
            original_path=filepath,
            contract_type=metadata.get("contract_type"),
            counterparty=metadata.get("counterparty"),
            jurisdiction=metadata.get("jurisdiction"),
            signature_date=metadata.get("signature_date"),
            expiration_date=metadata.get("expiration_date"),
            amount=metadata.get("amount"),
            currency=metadata.get("currency"),
            has_signature=metadata.get("has_signature", False),
            risk_level=risk_level,
            summary=summary,
            clauses_checklist=json.dumps(clauses_result, ensure_ascii=False),
            uploaded_by=current_user.id,
        )
        db.add(contract)
        db.commit()
        db.refresh(contract)

        # Indexar en Qdrant
        chunks = chunk_text(text)
        metadata["risk_level"] = risk_level
        point_ids = index_contract(contract.id, chunks, metadata)

        # Guardar IDs de vectores
        contract.qdrant_ids = json.dumps(point_ids)
        db.commit()

        # Log de actividad
        db.add(ActivityLog(
            user_id=current_user.id,
            action="upload",
            contract_id=contract.id,
            details=f"Cargado: {file.filename} | Chunks: {len(chunks)}",
        ))
        db.commit()

        return {
            "status": "ok",
            "contract_id": contract.id,
            "filename": file.filename,
            "chunks_indexed": len(chunks),
            "metadata": metadata,
            "summary": summary,
            "clauses": clauses_result,
        }

    except HTTPException:
        raise
    except Exception as e:
        ##mosrar el errorc completo
        logger.error(f"Error procesando documento: {str(e)}", exc_info=True)
        # Limpiar archivo si falla el procesamiento
        if os.path.exists(filepath):
            os.remove(filepath)
        raise HTTPException(500, f"Error procesando documento: {str(e)}")


@router.get("/list")
async def list_contracts(
    db: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Lista todos los contratos."""
    contracts = db.exec(select(Contract)).all()
    return contracts


@router.delete("/{contract_id}")
async def delete_contract(
    contract_id: int,
    db: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Elimina un contrato (solo admin)."""
    if current_user.role != "admin":
        raise HTTPException(403, "Solo administradores pueden eliminar contratos")

    contract = db.get(Contract, contract_id)
    if not contract:
        raise HTTPException(404, "Contrato no encontrado")

    # Eliminar vectores
    if contract.qdrant_ids:
        from services.rag_service import delete_contract_vectors
        ids = json.loads(contract.qdrant_ids)
        delete_contract_vectors(ids)

    # Eliminar archivo
    if os.path.exists(contract.original_path):
        os.remove(contract.original_path)

    db.delete(contract)
    db.commit()

    return {"status": "ok", "deleted": contract_id}
