"""
Ruta: Ingesta de documentos
POST /ingest/upload
"""

import os
import json
import shutil
import logging
from pathlib import Path
from datetime import datetime, date

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from config import settings
from database import get_session, get_sync_session
from models import Contract, ActivityLog
from services.document_processor import extract_text, chunk_text, extract_metadata_heuristic, extract_metadata_with_llm
from services.rag_service import index_contract
from services.llm_service import summarize_contract, analyze_clauses
from routes.auth import get_current_user


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("API -docs")

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


def parse_date(value) -> date | None:
    """Convierte string 'YYYY-MM-DD' a date. Devuelve None si falla o ya es None."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except (ValueError, TypeError):
        return None


def process_contract_background(contract_id: int, filepath: str, filename: str, user_id: int):
    """Procesa el documento en segundo plano."""
    try:
        with get_sync_session() as db:
            contract = db.get(Contract, contract_id)
            if not contract:
                return

            # Extraer texto
            text = extract_text(filepath)
            if not text or len(text.strip()) < 50:
                contract.status = "error"
                db.commit()
                logger.error(f"No se pudo extraer texto del documento: {filename}")
                return

            # Extraer metadatos
            metadata = extract_metadata_with_llm(text)

            # Generar resumen y análisis de cláusulas
            summary = summarize_contract(text)
            clauses_result = analyze_clauses(text)

            # Determinar nivel de riesgo
            risk_level = clauses_result.get("overall_risk", "unknown")

            # Actualizar contrato
            contract.contract_type = metadata.get("contract_type").lower()
            contract.party = metadata.get("party")
            contract.counterparty = metadata.get("counterparty")
            contract.jurisdiction = metadata.get("jurisdiction")
            contract.signature_date = parse_date(metadata.get("signature_date"))
            contract.expiration_date = parse_date(metadata.get("expiration_date"))
            contract.amount = metadata.get("amount")
            contract.currency = metadata.get("currency")
            contract.has_signature = metadata.get("has_signature", False)
            contract.risk_level = risk_level
            contract.summary = summary
            contract.clauses_checklist = json.dumps(clauses_result, ensure_ascii=False)
            contract.status = metadata.get("status", "active")
            db.commit()

            # Indexar en Qdrant
            chunks = chunk_text(text)
            metadata["risk_level"] = risk_level
            point_ids = index_contract(contract.id, chunks, metadata)

            # Guardar IDs de vectores
            contract.qdrant_ids = json.dumps(point_ids)
            db.commit()

            # Log de actividad
            db.add(ActivityLog(
                user_id=user_id,
                action="upload_completed",
                contract_id=contract.id,
                details=f"Procesado: {filename} | Chunks: {len(chunks)}",
            ))
            db.commit()

    except Exception as e:
        logger.error(f"Error procesando documento {filename}: {str(e)}", exc_info=True)
        # Marcar contrato como error y limpiar archivo si falla
        try:
            with get_sync_session() as db:
                contract = db.get(Contract, contract_id)
                if contract:
                    contract.status = "error"
                    db.commit()
        except Exception:
            pass
        if os.path.exists(filepath):
            os.remove(filepath)


@router.post("/upload")
async def upload_contract(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Carga un contrato y lo encola para procesamiento."""
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

    # Crear contrato en BD en estado pending
    contract = Contract(
        filename=file.filename,
        original_path=filepath,
        status="pending",
        uploaded_by=current_user.id,
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)

    # Log de actividad inicial
    db.add(ActivityLog(
        user_id=current_user.id,
        action="upload",
        contract_id=contract.id,
        details=f"Cargado y encolado: {file.filename}",
    ))
    db.commit()

    # Iniciar tarea en segundo plano
    background_tasks.add_task(process_contract_background, contract.id, filepath, file.filename, current_user.id)

    return {
        "status": "processing",
        "contract_id": contract.id,
        "filename": file.filename,
        "message": "Archivo recibido y procesando en segundo plano"
    }


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


@router.get("/{contract_id}/download")
async def download_contract(
    contract_id: int,
    db: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Descarga el archivo del contrato."""
    contract = db.get(Contract, contract_id)
    if not contract:
        raise HTTPException(404, "Contrato no encontrado")

    if not os.path.exists(contract.original_path):
        raise HTTPException(404, "Archivo físico no encontrado")

    return FileResponse(
        path=contract.original_path,
        filename=contract.filename,
        media_type="application/octet-stream"
    )


@router.get("/{contract_id}/text")
async def get_contract_text(
    contract_id: int,
    db: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Retorna el texto completo extraído del contrato."""
    contract = db.get(Contract, contract_id)
    if not contract:
        raise HTTPException(404, "Contrato no encontrado")

    if not os.path.exists(contract.original_path):
        raise HTTPException(404, "Archivo físico no encontrado")

    try:
        text = extract_text(contract.original_path)
        return {"text": text}
    except Exception as e:
        raise HTTPException(500, f"Error al extraer texto: {str(e)}")