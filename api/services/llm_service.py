"""
Servicio LLM — Consultas al modelo vía Ollama
"""

import json
from pathlib import Path
from typing import Optional

import ollama as ollama_client

from config import settings

# Cliente con el host correcto (por defecto usaría localhost, no el contenedor ollama)
_client = ollama_client.Client(host=settings.ollama_url)


def load_prompt(name: str) -> str:
    """Carga un prompt desde el directorio de prompts."""
    path = Path(settings.prompts_dir) / f"{name}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def chat_with_context(
    question: str,
    context_chunks: list[dict],
    system_prompt: Optional[str] = None,
) -> str:
    """
    Consulta el LLM con contexto recuperado del RAG.
    """
    if not system_prompt:
        system_prompt = load_prompt("system_base") or """
Eres un analista legal senior corporativo con más de 20 años de experiencia.
Responde EXCLUSIVAMENTE usando la información contenida en los documentos proporcionados.
Si no encuentras información suficiente, indícalo claramente.
No emitas asesoría legal definitiva ni reemplaces la revisión humana de un abogado.
Siempre cita el fragmento del documento del que extraes la información.
Responde en español.
""".strip()

    # Construir contexto
    context_text = "\n\n---\n\n".join([
        f"[Contrato ID: {c['contract_id']} | Tipo: {c.get('contract_type', 'N/A')} | Contraparte: {c.get('counterparty', 'N/A')}]\n{c['chunk_text']}"
        for c in context_chunks
    ])

    user_message = f"""Documentos relevantes:

{context_text}

---

Pregunta: {question}"""

    response = _client.chat(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        options={"temperature": 0.1, "num_ctx": 4096},
    )

    return response["message"]["content"]


def summarize_contract(text: str) -> str:
    """Genera resumen ejecutivo de un contrato."""
    prompt = load_prompt("summarize") or """
Analiza el siguiente contrato y genera un resumen ejecutivo estructurado con:

1. **Partes involucradas**: Quiénes firman
2. **Objeto del contrato**: Qué se acuerda
3. **Obligaciones principales**: De cada parte
4. **Fechas clave**: Firma, vigencia, vencimiento
5. **Monto**: Si aplica
6. **Cláusulas críticas**: Las más importantes
7. **Riesgos potenciales**: Lo que llama la atención

Sé conciso pero completo. Responde en español.
""".strip()

    response = _client.chat(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Contrato:\n\n{text[:6000]}"},
        ],
        options={"temperature": 0.1, "num_ctx": 4096},
    )
    return response["message"]["content"]


def analyze_clauses(text: str) -> dict:
    """Analiza cláusulas críticas y retorna checklist."""
    prompt = """
Analiza el siguiente contrato y verifica la presencia y adecuación de estas cláusulas.
Para cada una, responde con: "presente", "incompleta", "ausente", o "riesgo".
También agrega una observación breve.

Cláusulas a revisar:
1. Confidencialidad
2. Responsabilidad / limitación de responsabilidad
3. Penalizaciones / incumplimiento
4. Jurisdicción / ley aplicable
5. Terminación anticipada
6. Renovación automática
7. Fuerza mayor
8. Cesión de derechos
9. Propiedad intelectual (si aplica)
10. Protección de datos personales

Responde en formato JSON estricto:
{
  "clauses": [
    {"name": "Confidencialidad", "status": "presente", "observation": "..."},
    ...
  ],
  "overall_risk": "low|medium|high",
  "summary_observations": "..."
}
""".strip()

    response = _client.chat(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Contrato:\n\n{text[:6000]}"},
        ],
        options={"temperature": 0.1, "num_ctx": 4096},
    )

    content = response["message"]["content"]
    # Extraer JSON de la respuesta
    try:
        start = content.index("{")
        end = content.rindex("}") + 1
        return json.loads(content[start:end])
    except Exception:
        return {"raw_response": content, "error": "No se pudo parsear JSON"}
