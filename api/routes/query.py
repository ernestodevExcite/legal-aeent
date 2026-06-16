"""
Ruta: Motor de consulta (chat legal)
POST /query/ask
POST /query/search
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlmodel import Session

from database import get_session
from models import ActivityLog
from services.rag_service import search_contracts
from services.llm_service import chat_with_context
from routes.auth import get_current_user

router = APIRouter()


class QueryRequest(BaseModel):
    question: str
    contract_type: Optional[str] = None
    counterparty: Optional[str] = None
    risk_level: Optional[str] = None
    jurisdiction: Optional[str] = None
    has_signature: Optional[bool] = None
    search_type: str = "semantic"
    limit: int = 4


class SearchRequest(BaseModel):
    query: str
    contract_type: Optional[str] = None
    counterparty: Optional[str] = None
    risk_level: Optional[str] = None
    jurisdiction: Optional[str] = None
    has_signature: Optional[bool] = None
    search_type: str = "semantic"
    limit: int = 10


@router.post("/ask")
async def ask_legal(
    request: QueryRequest,
    db: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """
    Chat legal con RAG.
    Recupera fragmentos relevantes y genera respuesta con el LLM.
    """
    if not request.question.strip():
        raise HTTPException(400, "La pregunta no puede estar vacía")

    chunks = search_contracts(
        query=request.question,
        limit=request.limit,
        contract_type=request.contract_type,
        counterparty=request.counterparty,
        risk_level=request.risk_level,
        jurisdiction=request.jurisdiction,
        has_signature=request.has_signature,
        search_type=request.search_type,
    )

    if not chunks:
        return {
            "answer": "No encontré documentos relevantes para tu consulta. Verifica que los contratos estén cargados correctamente.",
            "sources": [],
        }

    # Consultar LLM con contexto
    answer = chat_with_context(
        question=request.question,
        context_chunks=chunks,
    )

    # Fuentes únicas
    sources = list({c["contract_id"] for c in chunks})

    # Log
    db.add(ActivityLog(
        user_id=current_user.id,
        action="query",
        details=f"Pregunta: {request.question[:100]}",
    ))
    db.commit()

    return {
        "answer": answer,
        "sources": sources,
        "chunks_used": len(chunks),
    }


@router.post("/search")
async def semantic_search(
    request: SearchRequest,
    current_user=Depends(get_current_user),
):
    """Búsqueda semántica pura sin LLM."""
    results = search_contracts(
        query=request.query,
        limit=request.limit,
        contract_type=request.contract_type,
        counterparty=request.counterparty,
        risk_level=request.risk_level,
        jurisdiction=request.jurisdiction,
        has_signature=request.has_signature,
        search_type=request.search_type,
    )
    return {"results": results, "total": len(results)}

@router.post("/filter")
async def filter_contracts(
    contract_type: Optional[str] = None,
    counterparty: Optional[str] = None,
    risk_level: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    has_signature: Optional[bool] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_session),
    current_user=Depends(get_current_user),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """Filtrado de contratos por metadatos sin búsqueda semántica."""
    query = db.query(Contract).filter(Contract.user_id == current_user.id)

    if contract_type and contract_type.strip():
        query = query.filter(Contract.contract_type.ilike(f"%{contract_type.strip()}%"))
        
    if counterparty and counterparty.strip():
        query = query.filter(Contract.counterparty.ilike(f"%{counterparty.strip()}%"))
        
    if risk_level and risk_level.strip() and risk_level.lower() != "todos":
        query = query.filter(Contract.risk_level.ilike(f"%{risk_level.strip()}%"))
        
    if jurisdiction and jurisdiction.strip():
        query = query.filter(Contract.jurisdiction.ilike(f"%{jurisdiction.strip()}%"))
        
    if has_signature is not None:
        query = query.filter(Contract.has_signature == has_signature)

    if status and status.strip():
        query = query.filter(Contract.status.ilike(f"%{status.strip()}%"))
    
    if start_date and end_date:
        query = query.filter(Contract.created_at >= start_date, Contract.created_at <= end_date)

    results = query.all()
    
    return {"contracts": [r.to_dict() for r in results], "total": len(results)}
