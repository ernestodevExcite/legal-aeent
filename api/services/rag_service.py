"""
Servicio RAG — Vectorización e indexación en Qdrant
"""

import json
import uuid
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, Range
)
import ollama as ollama_client

from config import settings

# Cliente apuntando al contenedor ollama, no a localhost
_ollama = ollama_client.Client(host=settings.ollama_url)


def get_qdrant() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url)


def ensure_collection():
    """Crea la colección si no existe."""
    client = get_qdrant()
    existing = [c.name for c in client.get_collections().collections]
    if settings.collection_name not in existing:
        client.create_collection(
            collection_name=settings.collection_name,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )
    return client


def embed_text(text: str) -> list[float]:
    """Genera embedding usando Ollama."""
    response = _ollama.embeddings(
        model=settings.embed_model,
        prompt=text
    )
    return response["embedding"]


def index_contract(contract_id: int, chunks: list[str], metadata: dict) -> list[str]:
    """
    Vectoriza e indexa todos los chunks de un contrato.
    Retorna lista de IDs de puntos en Qdrant.
    """
    client = ensure_collection()
    point_ids = []

    for i, chunk in enumerate(chunks):
        try:
            vector = embed_text(chunk)
            point_id = str(uuid.uuid4())
            client.upsert(
                collection_name=settings.collection_name,
                points=[PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "contract_id": contract_id,
                        "chunk_index": i,
                        "chunk_text": chunk,
                        "contract_type": metadata.get("contract_type"),
                        "counterparty": metadata.get("counterparty"),
                        "expiration_date": metadata.get("expiration_date"),
                        "risk_level": metadata.get("risk_level", "unknown"),
                        "confidentiality_level": metadata.get("confidentiality_level", "internal"),
                    }
                )]
            )
            point_ids.append(point_id)
        except Exception as e:
            print(f"Error indexando chunk {i}: {e}")

    return point_ids


def search_contracts(
    query: str,
    limit: int = 8,
    contract_type: Optional[str] = None,
    counterparty: Optional[str] = None,
    user_permissions: Optional[list[str]] = None,
) -> list[dict]:
    """
    Búsqueda semántica + filtros de metadatos.
    """
    client = ensure_collection()
    query_vector = embed_text(query)

    # Construir filtros
    must_conditions = []
    if contract_type:
        must_conditions.append(
            FieldCondition(key="contract_type", match=MatchValue(value=contract_type))
        )
    if counterparty:
        must_conditions.append(
            FieldCondition(key="counterparty", match=MatchValue(value=counterparty))
        )

    query_filter = Filter(must=must_conditions) if must_conditions else None

    results = client.search(
        collection_name=settings.collection_name,
        query_vector=query_vector,
        limit=limit,
        query_filter=query_filter,
        with_payload=True,
    )

    return [
        {
            "score": r.score,
            "chunk_text": r.payload.get("chunk_text"),
            "contract_id": r.payload.get("contract_id"),
            "contract_type": r.payload.get("contract_type"),
            "counterparty": r.payload.get("counterparty"),
        }
        for r in results
    ]


def delete_contract_vectors(qdrant_ids: list[str]):
    """Elimina los vectores de un contrato."""
    client = get_qdrant()
    client.delete(
        collection_name=settings.collection_name,
        points_selector=qdrant_ids
    )
