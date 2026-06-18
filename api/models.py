"""
Modelos de base de datos y esquemas
"""

from datetime import datetime, date
from typing import Optional
from sqlmodel import SQLModel, Field


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    name: str
    role: str = "lawyer"  # admin | legal_director | lawyer | internal_user | auditor
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Contract(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str
    original_path: str
    contract_type: Optional[str] = None       # suministro, servicios, nda, compra, colaboración
    counterparty: Optional[str] = None        # nombre contraparte
    party: Optional[str] = None
    jurisdiction: Optional[str] = None
    signature_date: Optional[date] = None
    expiration_date: Optional[date] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    risk_level: str = "unknown"               # low | medium | high | unknown
    confidentiality_level: str = "internal"  # public_internal | restricted | confidential | highly_confidential
    status: str = "active"                    # active | expired | pending | archived
    has_signature: bool = False
    summary: Optional[str] = None
    clauses_checklist: Optional[str] = None   # JSON string
    qdrant_ids: Optional[str] = None          # JSON string con IDs de chunks
    uploaded_by: Optional[int] = Field(default=None, foreign_key="user.id")
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ActivityLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    action: str                               # upload | query | analyze | export | login
    contract_id: Optional[int] = None
    details: Optional[str] = None
    ip_address: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Alert(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    contract_id: int = Field(foreign_key="contract.id")
    alert_type: str                           # expiring_90 | expiring_60 | expiring_30 | no_date | no_signature | risk
    message: str
    sent: bool = False
    sent_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
