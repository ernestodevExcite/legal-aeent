"""
Servicio de procesamiento de documentos
PDF, DOCX, OCR → texto limpio + metadatos
"""

import os
import json
import re
from pathlib import Path
from datetime import date
from typing import Optional

import pdfplumber
import pytesseract
from pdf2image import convert_from_path
from docx import Document
from PIL import Image

from config import settings


def extract_text_from_pdf(filepath: str) -> str:
    """Extrae texto de PDF. Si está escaneado, usa OCR."""
    text = ""
    try:
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception:
        pass

    # Si no se extrajo texto suficiente, intentar OCR
    if len(text.strip()) < 100:
        try:
            images = convert_from_path(filepath, dpi=200)
            for img in images:
                text += pytesseract.image_to_string(img, lang="spa") + "\n"
        except Exception:
            pass

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
