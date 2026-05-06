"""
Autenticación JWT
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlmodel import Session, select

from config import settings
from database import get_session
from models import User

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


class Token(BaseModel):
    access_token: str
    token_type: str


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_session),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        email: str = payload.get("sub")
        if not email:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.exec(select(User).where(User.email == email)).first()
    if not user or not user.is_active:
        raise credentials_exception
    return user


@router.post("/login", response_model=Token)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_session),
):
    user = db.exec(select(User).where(User.email == form.username)).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(401, "Credenciales incorrectas")
    token = create_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/register")
async def register(
    email: str,
    password: str,
    name: str,
    role: str = "lawyer",
    db: Session = Depends(get_session),
):
    """Registro de usuarios (en MVP solo admin puede crear usuarios — simplificado aquí)."""
    existing = db.exec(select(User).where(User.email == email)).first()
    if existing:
        raise HTTPException(400, "Email ya registrado")
    user = User(
        email=email,
        hashed_password=hash_password(password),
        name=name,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"status": "ok", "user_id": user.id, "email": user.email}
