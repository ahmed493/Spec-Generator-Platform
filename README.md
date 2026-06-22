# Spec Generator Platform

Plateforme de génération automatique de spécifications techniques et fonctionnelles.

## Architecture

```
spec-generator/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── api/
│   │   └── routes.py        # API endpoints (16+ vector store endpoints)
│   ├── mcp_servers/
│   │   └── github_server.py # MCP GitHub connector
│   ├── agents/
│   │   ├── llm_client.py    # LLM abstraction (Ollama/OpenAI/Claude)
│   │   └── spec_agent.py    # Spec generation agent
│   ├── vectorstore/         # NEW: Vector store & semantic search
│   │   ├── vector_manager.py    # ChromaDB orchestrator
│   │   ├── chunking_strategy.py # Intelligent chunking
│   │   ├── embeddings.py        # Sentence Transformers
│   │   └── retrieval.py         # Retrieval-Augmented Extraction
│   └── config/
│       └── settings.py      # Configuration
├── requirements.txt
├── VECTOR_STORE_QUICKSTART.md    # NEW: Quick start guide
├── VECTOR_STORE_GUIDE.md         # NEW: Comprehensive guide
├── VECTOR_STORE_CONFIG.md        # NEW: Configuration options
└── README.md
```

## Installation

```bash
cd spec-generator
pip install -r requirements.txt
```

## Configuration

1. Créez un fichier `.env` à la racine du projet et configurez les variables nécessaires :
```env
# GitHub Token
GITHUB_TOKEN=ghp_your_token_here

# LLM Provider: "ollama", "openai", ou "anthropic"
LLM_PROVIDER=openai


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

Dans `.env` :
```env
# Pour OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key

# Pour Anthropic
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-your-key
```
