"""
Ruta: Análisis de cláusulas
POST /analyze/{contract_id}
GET  /analyze/{contract_id}/summary
"""

import json
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from database import get_session
from models import Contract, ActivityLog
from services.document_processor import extract_text
from services.llm_service import summarize_contract, analyze_clauses
from routes.auth import get_current_user

router = APIRouter()


@router.get("/{contract_id}")
async def get_analysis(
    contract_id: int,
    db: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Retorna análisis completo de un contrato ya procesado."""
    contract = db.get(Contract, contract_id)
    if not contract:
        raise HTTPException(404, "Contrato no encontrado")

    clauses = {}
    if contract.clauses_checklist:
        try:
            clauses = json.loads(contract.clauses_checklist)
        except Exception:
            pass

    return {
        "contract_id": contract_id,
        "filename": contract.filename,
        "summary": contract.summary,
        "clauses": clauses,
        "risk_level": contract.risk_level,
        "metadata": {
            "contract_type": contract.contract_type,
            "counterparty": contract.counterparty,
            "signature_date": str(contract.signature_date) if contract.signature_date else None,
            "expiration_date": str(contract.expiration_date) if contract.expiration_date else None,
            "jurisdiction": contract.jurisdiction,
            "amount": contract.amount,
        }
    }


@router.post("/{contract_id}/reanalyze")
async def reanalyze_contract(
    contract_id: int,
    db: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Re-analiza un contrato (útil si cambió el prompt o el modelo)."""
    if current_user.role not in ["admin", "legal_director", "lawyer"]:
        raise HTTPException(403, "Sin permisos para re-analizar")

    contract = db.get(Contract, contract_id)
    if not contract:
        raise HTTPException(404, "Contrato no encontrado")

    text = extract_text(contract.original_path)
    summary = summarize_contract(text)
    clauses_result = analyze_clauses(text)
    risk_level = clauses_result.get("overall_risk", "unknown")

    contract.summary = summary
    contract.clauses_checklist = json.dumps(clauses_result, ensure_ascii=False)
    contract.risk_level = risk_level
    db.commit()

    db.add(ActivityLog(
        user_id=current_user.id,
        action="analyze",
        contract_id=contract_id,
        details="Re-análisis manual",
    ))
    db.commit()

    return {
        "status": "ok",
        "contract_id": contract_id,
        "summary": summary,
        "clauses": clauses_result,
        "risk_level": risk_level,
    }
