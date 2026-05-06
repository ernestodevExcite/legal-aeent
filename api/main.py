"""
Agente Legal MVP - Backend Principal
FastAPI + RAG + Qdrant + Ollama
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from config import settings
from database import init_db
from routes import ingest, query, analyze, alerts, reports, auth
from services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()


app = FastAPI(
    title="Agente Legal MVP",
    description="Asistente legal privado para análisis contractual",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rutas
app.include_router(auth.router,     prefix="/auth",     tags=["Autenticación"])
app.include_router(ingest.router,   prefix="/ingest",   tags=["Ingesta"])
app.include_router(query.router,    prefix="/query",    tags=["Consultas"])
app.include_router(analyze.router,  prefix="/analyze",  tags=["Análisis"])
app.include_router(alerts.router,   prefix="/alerts",   tags=["Alertas"])
app.include_router(reports.router,  prefix="/reports",  tags=["Reportes"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
