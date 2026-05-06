"""
Sistema de alertas de vencimiento y riesgo
"""

from datetime import datetime, date, timedelta
from typing import Optional
import aiosmtplib
from email.mime.text import MIMEText
import httpx

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from config import settings
from database import get_session
from models import Contract, Alert
from routes.auth import get_current_user

router = APIRouter()


async def send_email_alert(subject: str, body: str):
    """Envía alerta por correo."""
    if not settings.smtp_host or not settings.alert_email:
        return False
    try:
        msg = MIMEText(body, "html", "utf-8")
        msg["Subject"] = subject
        msg["From"] = settings.smtp_user
        msg["To"] = settings.alert_email
        async with aiosmtplib.SMTP(
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            use_tls=False,
            start_tls=True,
        ) as smtp:
            await smtp.login(settings.smtp_user, settings.smtp_pass)
            await smtp.send_message(msg)
        return True
    except Exception as e:
        print(f"Error enviando email: {e}")
        return False


async def send_slack_alert(message: str):
    """Envía alerta a Slack via webhook."""
    if not settings.slack_webhook:
        return False
    try:
        async with httpx.AsyncClient() as client:
            await client.post(settings.slack_webhook, json={"text": message})
        return True
    except Exception as e:
        print(f"Error enviando Slack: {e}")
        return False


def check_expiring_contracts(db: Session):
    """Revisa contratos por vencer y genera alertas."""
    today = date.today()
    thresholds = [90, 60, 30]
    alerts_created = []

    contracts = db.exec(select(Contract).where(Contract.status == "active")).all()

    for contract in contracts:
        if not contract.expiration_date:
            # Sin fecha de vencimiento
            existing = db.exec(
                select(Alert).where(
                    Alert.contract_id == contract.id,
                    Alert.alert_type == "no_date",
                )
            ).first()
            if not existing:
                alert = Alert(
                    contract_id=contract.id,
                    alert_type="no_date",
                    message=f"Contrato '{contract.filename}' no tiene fecha de vencimiento registrada.",
                )
                db.add(alert)
                alerts_created.append(alert)
            continue

        days_left = (contract.expiration_date - today).days

        for threshold in thresholds:
            if 0 <= days_left <= threshold:
                alert_type = f"expiring_{threshold}"
                existing = db.exec(
                    select(Alert).where(
                        Alert.contract_id == contract.id,
                        Alert.alert_type == alert_type,
                    )
                ).first()
                if not existing:
                    alert = Alert(
                        contract_id=contract.id,
                        alert_type=alert_type,
                        message=f"⚠️ Contrato '{contract.filename}' vence en {days_left} días ({contract.expiration_date}). Contraparte: {contract.counterparty or 'N/A'}",
                    )
                    db.add(alert)
                    alerts_created.append(alert)
                    break  # Solo la alerta más urgente

        # Marcar como expirado
        if days_left < 0 and contract.status == "active":
            contract.status = "expired"

    # Sin firma detectada
    for contract in contracts:
        if not contract.has_signature:
            existing = db.exec(
                select(Alert).where(
                    Alert.contract_id == contract.id,
                    Alert.alert_type == "no_signature",
                )
            ).first()
            if not existing:
                alert = Alert(
                    contract_id=contract.id,
                    alert_type="no_signature",
                    message=f"Contrato '{contract.filename}' no tiene firma detectada.",
                )
                db.add(alert)
                alerts_created.append(alert)

    db.commit()
    return alerts_created


@router.get("/")
async def get_alerts(
    db: Session = Depends(get_session),
    current_user=Depends(get_current_user),
    unsent_only: bool = False,
):
    """Lista todas las alertas."""
    query = select(Alert)
    if unsent_only:
        query = query.where(Alert.sent == False)
    return db.exec(query.order_by(Alert.created_at.desc())).all()


@router.post("/run")
async def run_alert_check(
    db: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Ejecuta revisión manual de alertas."""
    alerts = check_expiring_contracts(db)
    return {
        "status": "ok",
        "alerts_generated": len(alerts),
        "alerts": [a.message for a in alerts]
    }
