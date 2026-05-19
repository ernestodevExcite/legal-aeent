"""
Servicio de procesamiento de documentos
PDF, DOCX, OCR → texto limpio + metadatos
"""

import os
import json
import ollama
import re
from pathlib import Path
from datetime import date
from typing import Optional

import fitz
from concurrent.futures import ThreadPoolExecutor
import pytesseract
from pdf2image import convert_from_path
from docx import Document
from PIL import Image

from config import settings

# Cliente apuntando al contenedor ollama, no a localhost
_ollama = ollama.Client(host=settings.ollama_url)


def process_image_ocr(img):
    """Procesa una sola imagen con OCR."""
    return pytesseract.image_to_string(img, lang="spa")

def extract_text_from_pdf(filepath: str) -> str:
    """Extrae texto de PDF. Usa OCR en paralelo si está escaneado."""
    text = ""
    try:
        # Extraer con PyMuPDF (muy rápido)
        doc = fitz.open(filepath)
        for page in doc:
            page_text = page.get_text()
            if page_text:
                text += page_text + "\n"
        doc.close()
    except Exception as e:
        print(f"Error extrayendo texto nativo: {e}")

    # Si no se extrajo texto suficiente, intentar OCR en paralelo
    if len(text.strip()) < 100:
        try:
            images = convert_from_path(filepath, dpi=200)
            text_chunks = []
            
            # Usar hilos paralelos para acelerar el OCR
            with ThreadPoolExecutor(max_workers=4) as executor:
                results = executor.map(process_image_ocr, images)
                text_chunks = list(results)
                
            text = "\n".join(text_chunks)
        except Exception as e:
            print(f"Error en OCR: {e}")

    return text.strip()


def extract_text_from_docx(filepath: str) -> str:
    """Extrae texto de Word."""
    doc = Document(filepath)
    return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])


def extract_text(filepath: str) -> str:
    """Extrae texto según extensión."""
    ext = Path(filepath).suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(filepath)
    elif ext in [".docx", ".doc"]:
        return extract_text_from_docx(filepath)
    else:
        raise ValueError(f"Formato no soportado: {ext}")


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    """Divide el texto en chunks con overlap para RAG."""
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def extract_metadata_heuristic(text: str) -> dict:
    """
    Extrae metadatos básicos del texto usando expresiones regulares.
    En fases posteriores esto puede mejorar con el LLM.
    """
    metadata = {
        "contract_type": None,
        "counterparty": None,
        "signature_date": None,
        "expiration_date": None,
        "amount": None,
        "currency": None,
        "has_signature": False,
        "jurisdiction": None,
    }

    text_lower = text.lower()

    # Tipo de contrato
    types_map = {
        "nda": ["confidencialidad", "nda", "non-disclosure"],
        "servicios": ["prestación de servicios", "contrato de servicios"],
        "suministro": ["suministro", "abastecimiento"],
        "compra": ["compraventa", "contrato de compra"],
        "colaboración": ["colaboración", "alianza estratégica"],
        "arrendamiento": ["arrendamiento", "renta"],
    }
    for ctype, keywords in types_map.items():
        if any(k in text_lower for k in keywords):
            metadata["contract_type"] = ctype
            break

    # Fechas (formato DD/MM/YYYY o DD de mes de YYYY)
    date_patterns = [
        r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b",
        r"\b(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})\b",
    ]
    months_es = {
        "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
        "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
        "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12"
    }
    dates_found = []
    for pattern in date_patterns:
        matches = re.findall(pattern, text_lower)
        for m in matches:
            try:
                if len(m) == 3:
                    day, month, year = m
                    if month in months_es:
                        month = months_es[month]
                    d = date(int(year), int(month), int(day))
                    dates_found.append(d)
            except Exception:
                pass
    if dates_found:
        dates_found.sort()
        metadata["signature_date"] = str(dates_found[0])
        if len(dates_found) > 1:
            metadata["expiration_date"] = str(dates_found[-1])

    # Montos
    amount_match = re.search(r"\$\s*([\d,]+(?:\.\d{2})?)", text)
    if amount_match:
        metadata["amount"] = float(amount_match.group(1).replace(",", ""))
        metadata["currency"] = "USD"

    # Firma detectada
    if any(k in text_lower for k in ["firma", "firmado", "rúbrica", "suscrito"]):
        metadata["has_signature"] = True

    # Jurisdicción básica
    for country in ["méxico", "mexico", "colombia", "argentina", "españa", "chile", "perú", "peru"]:
        if country in text_lower:
            metadata["jurisdiction"] = country.capitalize()
            break

    return metadata

def extract_metadata_with_llm(text_fragment: str) -> dict:
    # prompt = f"""
    # Analiza el siguiente extracto de contrato y extrae la información en formato JSON:
    # {{
    #     "contract_type": "tipo de contrato, ejemplos: nda, de servicios, suministro, compra, colaboración, arrendamiento etc",
    #     "counterparty": "nombre de la contraparte",
    #     "signature_date": "Fecha de firma del contrato en formato YYYY-MM-DD",
    #     "expiration_date": "Fecha de vencimiento del contrato en formato YYYY-MM-DD",
    #     "amount": 0.0,
    #     "currency": "ISO code",
    #     "jurisdiction": "país"
    # }}
    
    # Texto: {text_fragment[:5000]} # Enviamos los primeros 3000 caracteres
    # """
    prompt = f"""
    Actúa como un abogado experto en derecho contractual. 
    Tu tarea es extraer información clave de un contrato y devolverla en formato JSON.

    Aquí están las reglas:
    1. Analiza el texto y extrae solo la información que puedas validar con certeza.
    2. Si un campo no está presente en el texto, déjalo como null.
    3. No inventes datos. Si no encuentras un valor claro, usa null.
    4. Para fechas usa el formato YYYY-MM-DD, si no hay fecha, déjalo como null. puede haber periodos como de (1 de enero) a (31 de diciembre de 2022).
    5. Para montos numéricos elimina comas y símbolos de moneda.
    6. Para el tipo de contrato sé específico (ej. “arrendamiento”, “compraventa”, “NDA”, “prestación de servicios”, “suministro”, “colaboración”, “arrendamiento”, “renta”, etc.).
    7. No incluyas comentarios o explicaciones, solo el JSON.

    Texto del contrato:
    {text_fragment}

    Devuelve únicamente un objeto JSON válido con estas claves:
    {{
        "contract_type": "tipo de contrato",
        "counterparty": "nombre de la contraparte",
        "signature_date": "fecha en formato YYYY-MM-DD",
        "expiration_date": "fecha en formato YYYY-MM-DD",
        "amount": 0.0,
        "currency": "ISO code",
        "jurisdiction": "país"
    }}
    """
    
    try:
        response = _ollama.generate(
            model=settings.llm_model,
            prompt=prompt,
            format="json",
            stream=False
        )
        return json.loads(response['response'])
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"LLM failed, falling back to heuristic for: {e}")
        return extract_metadata_heuristic(text_fragment)