# Spec Generator Platform

Plateforme de génération automatique de spécifications techniques et fonctionnelles.

## Architecture

```
spec-generator/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── api/
│   │   └── routes.py        # API endpoints
│   ├── mcp_servers/
│   │   └── github_server.py # MCP GitHub connector
│   ├── agents/
│   │   ├── llm_client.py    # LLM abstraction (Ollama/OpenAI/Claude)
│   │   └── spec_agent.py    # Spec generation agent
│   └── config/
│       └── settings.py      # Configuration
├── templates/
├── requirements.txt
├── .env.example
└── README.md
```

## Installation

```bash
cd spec-generator
pip install -r requirements.txt
```

## Configuration

1. Copier `.env.example` en `.env`:
```bash
cp .env.example .env
```

2. Configurer les variables:
```env
# GitHub Token (requis)
GITHUB_TOKEN=ghp_your_token_here

# LLM Provider: "ollama", "openai", ou "anthropic"
LLM_PROVIDER=ollama

# Si Ollama (local)
OLLAMA_MODEL=llama3.1
```

## Lancer Ollama (si pas déjà fait)

```bash
# Télécharger un modèle
ollama pull llama3.1

# Vérifier qu'Ollama tourne
ollama list
```

## Lancer le serveur

```bash
cd spec-generator
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API Endpoints

### Connexion
- `POST /api/connect/github` - Connecter GitHub
- `GET /api/connections` - Status des connexions

### GitHub
- `POST /api/github/repo-structure` - Structure d'un repo
- `POST /api/github/repo-metadata` - Métadonnées complètes

### Génération
- `POST /api/generate-spec` - Générer une spec
- `POST /api/chat` - Chatbot Q&A

### Health
- `GET /api/health` - Health check

## Exemple d'utilisation

```bash
# 1. Connecter GitHub
curl -X POST http://localhost:8000/api/connect/github \
  -H "Content-Type: application/json" \
  -d '{"token": "ghp_your_token"}'

# 2. Générer une spec
curl -X POST http://localhost:8000/api/generate-spec \
  -H "Content-Type: application/json" \
  -d '{"owner": "elabettayeb", "repo_name": "ecoloco-raw"}'

# 3. Poser une question
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Quelles sont les transformations dans ce repo?"}'
```

## Changer de LLM

Dans `.env`:
```env
# Pour OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key

# Pour Anthropic
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-your-key
```

## Prochaines étapes

- [ ] Ajouter MCP BigQuery
- [ ] Ajouter MCP PostgreSQL
- [ ] Ajouter MCP Power BI
- [ ] Ajouter MCP GCS
- [ ] Frontend React/Vue
