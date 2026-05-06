# ⚖️ Agente Legal MVP

Asistente legal privado para análisis contractual.
100% local · RAG + LLM · Sin datos en la nube.

## Stack

| Componente | Tecnología |
|---|---|
| LLM | Qwen2.5 7B via Ollama |
| Embeddings | nomic-embed-text |
| Vector store | Qdrant |
| Backend | FastAPI (Python) |
| Frontend | Streamlit |
| Base de datos | SQLite |
| Infra | Docker Compose |

## Requisitos mínimos

- Docker + Docker Compose
- 16 GB RAM
- 4 CPUs
- 20 GB almacenamiento

## Instalación rápida

```bash
git clone <repo>
cd legal-mvp
bash setup.sh
```

El script:
1. Levanta Ollama + Qdrant
2. Descarga los modelos (~5GB)
3. Levanta toda la plataforma
4. Muestra URLs de acceso

## Estructura

```
legal-mvp/
├── api/                    # FastAPI backend
│   ├── main.py             # App principal
│   ├── config.py           # Configuración
│   ├── database.py         # SQLite
│   ├── models.py           # Esquemas BD
│   ├── routes/
│   │   ├── auth.py         # JWT auth
│   │   ├── ingest.py       # Carga documentos
│   │   ├── query.py        # Chat legal RAG
│   │   ├── analyze.py      # Análisis cláusulas
│   │   ├── alerts.py       # Sistema alertas
│   │   └── reports.py      # Reportes + Excel
│   └── services/
│       ├── document_processor.py  # PDF/DOCX/OCR
│       ├── rag_service.py         # Qdrant + embeddings
│       ├── llm_service.py         # Ollama LLM
│       └── scheduler.py           # Cron diario
├── ui/                     # Streamlit frontend
│   └── app.py              # Dashboard + Chat + Carga
├── docker/
│   └── nginx.conf          # Reverse proxy
├── prompts/                # Prompts del sistema (editables)
├── data/                   # Contratos y BD (no en git)
├── docker-compose.yml
├── setup.sh                # Instalación automática
└── .env                    # Credenciales (no en git)
```

## URLs de acceso

| Servicio | URL |
|---|---|
| Interfaz web | http://localhost |
| API docs | http://localhost/api/docs |
| Qdrant dashboard | http://localhost:6333/dashboard |

## Primer usuario admin

```bash
curl -X POST http://localhost/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@tudespacho.com","password":"segura123","name":"Admin","role":"admin"}'
```

## Flujo de uso

1. Abrir `http://localhost`
2. Iniciar sesión
3. Ir a **Cargar Contratos** → subir PDFs/DOCX
4. El sistema procesa, extrae metadatos y analiza cláusulas automáticamente
5. Ir a **Chat Legal** → hacer preguntas sobre los contratos
6. Ver **Dashboard** para resumen y alertas

## Fases siguientes (post-MVP)

- [ ] Roles y permisos granulares
- [ ] Carga masiva desde carpeta / Google Drive
- [ ] Comparación contra plantillas
- [ ] Firma digital detección mejorada
- [ ] API para integraciones externas
- [ ] Módulo de licitaciones
