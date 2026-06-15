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
    limit: int = 4


class SearchRequest(BaseModel):
    query: str
    contract_type: Optional[str] = None
    counterparty: Optional[str] = None
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

    # Buscar fragmentos relevantes
    chunks = search_contracts(
        query=request.question,
        limit=request.limit,
        contract_type=request.contract_type,
        counterparty=request.counterparty,
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
    )
    return {"results": results, "total": len(results)}
