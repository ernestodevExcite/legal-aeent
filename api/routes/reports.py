"""
Reportes básicos — PDF y Excel
"""

import io
from datetime import date
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from database import get_session
from models import Contract
from routes.auth import get_current_user

router = APIRouter()


@router.get("/excel")
async def export_excel(
    db: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Exporta todos los contratos a Excel."""
    from openpyxl import Workbook

    contracts = db.exec(select(Contract)).all()
    wb = Workbook()
    ws = wb.active
    ws.title = "Contratos"

    headers = [
        "ID", "Archivo", "Tipo", "Contraparte", "Jurisdicción",
        "Fecha Firma", "Fecha Vencimiento", "Monto", "Moneda",
        "Riesgo", "Estado", "Tiene Firma"
    ]
    ws.append(headers)

    for c in contracts:
        ws.append([
            c.id, c.filename, c.contract_type, c.counterparty,
            c.jurisdiction, str(c.signature_date or ""), str(c.expiration_date or ""),
            c.amount, c.currency, c.risk_level, c.status,
            "Sí" if c.has_signature else "No"
        ])

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=contratos.xlsx"}
    )


@router.get("/summary")
async def get_summary(
    db: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Resumen ejecutivo de todos los contratos."""
    contracts = db.exec(select(Contract)).all()
    today = date.today()

    total = len(contracts)
    active = sum(1 for c in contracts if c.status == "active")
    expired = sum(1 for c in contracts if c.status == "expired")
    expiring_30 = sum(
        1 for c in contracts
        if c.expiration_date and 0 <= (c.expiration_date - today).days <= 30
    )
    expiring_90 = sum(
        1 for c in contracts
        if c.expiration_date and 0 <= (c.expiration_date - today).days <= 90
    )
    high_risk = sum(1 for c in contracts if c.risk_level == "high")
    no_date = sum(1 for c in contracts if not c.expiration_date)

    by_type = {}
    for c in contracts:
        t = c.contract_type or "sin clasificar"
        by_type[t] = by_type.get(t, 0) + 1

    by_counterparty = {}
    for c in contracts:
        cp = c.counterparty or "sin contraparte"
        by_counterparty[cp] = by_counterparty.get(cp, 0) + 1

    return {
        "total": total,
        "active": active,
        "expired": expired,
        "expiring_30_days": expiring_30,
        "expiring_90_days": expiring_90,
        "high_risk": high_risk,
        "no_expiration_date": no_date,
        "by_type": by_type,
        "by_counterparty": dict(sorted(by_counterparty.items(), key=lambda x: -x[1])[:10]),
    }
