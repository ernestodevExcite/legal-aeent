#!/bin/bash
# setup.sh — Script de instalación inicial del Agente Legal MVP
# Ejecutar como: bash setup.sh

set -e
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}⚖️  Agente Legal MVP — Setup inicial${NC}"
echo "================================================"

# Verificar Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker no instalado. Instálalo primero.${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null 2>&1; then
    echo -e "${RED}❌ Docker Compose no disponible.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Docker detectado${NC}"

# Crear .env si no existe
if [ ! -f .env ]; then
    echo -e "${YELLOW}📝 Creando .env...${NC}"
    cat > .env << 'EOF'
SECRET_KEY=JCIdVkQ+SvLtY1pFBtMWaOhk4Zjhi+vMn7Wgv0sUiao=
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
SLACK_WEBHOOK=
ALERT_EMAIL=
EOF
    echo -e "${GREEN}✅ .env creado. Edítalo con tus credenciales de email/Slack.${NC}"
fi

# Crear directorios de datos
mkdir -p data/raw data/processed

# Levantar infraestructura base primero
echo -e "${YELLOW}🐳 Iniciando Ollama y Qdrant...${NC}"
docker compose up -d ollama qdrant

# Esperar a que Ollama esté listo
echo -e "${YELLOW}⏳ Esperando a Ollama (puede tardar 30-60s)...${NC}"
for i in {1..30}; do
    if curl -s http://localhost:11434 > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Ollama listo${NC}"
        break
    fi
    sleep 3
    echo -n "."
done

# Descargar modelos
echo -e "${YELLOW}📥 Descargando modelos (puede tardar varios minutos)...${NC}"
echo "→ qwen2.5:7b (~4.7GB)"
docker exec legal_ollama ollama pull qwen2.5:7b

echo "→ nomic-embed-text (~274MB)"
docker exec legal_ollama ollama pull nomic-embed-text

echo -e "${GREEN}✅ Modelos descargados${NC}"

# Levantar el resto
echo -e "${YELLOW}🚀 Iniciando todos los servicios...${NC}"
docker compose up -d

echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}✅ Agente Legal MVP está corriendo!${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo "  🌐 Interfaz web:  http://localhost"
echo "  🔌 API docs:      http://localhost/api/docs"
echo "  📦 Qdrant UI:     http://localhost:6333/dashboard"
echo ""
echo -e "${YELLOW}Primer usuario (admin):${NC}"
echo "  curl -X POST http://localhost/api/auth/register \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"email\":\"admin@tudespacho.com\",\"password\":\"segura123\",\"name\":\"Admin\",\"role\":\"admin\"}'"
echo ""
echo -e "${GREEN}¡Listo para cargar contratos!${NC}"
