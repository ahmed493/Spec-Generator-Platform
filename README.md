# Spec Generator Platform

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI 0.109+](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![React 18.2+](https://img.shields.io/badge/React-18.2+-61DAFB.svg)](https://react.dev/)

Automatically generate technico-functional specifications from your codebase using a multi-agent LLM pipeline. Connect to GitHub repositories, data warehouses, and business intelligence tools to extract data and compose professional specification documents.

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Running the Project](#running-the-project)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [Configuration](#configuration)

## Architecture

### Technology Stack

Backend:
- FastAPI 0.109+
- SQLAlchemy 2.0 ORM (SQLite development, PostgreSQL production)
- ChromaDB 0.4.0 with SentenceTransformers 2.2.0 for vector embeddings
- LLM Support: OpenAI (gpt-4o-mini), Anthropic (claude-3-sonnet), Ollama (local)

Frontend:
- React 18.2 with Vite 5.0
- React Context API for state management
- Axios 1.6+ for HTTP requests

Data Integration:
- GitHub API
- PostgreSQL
- BigQuery
- Power BI
- Google Cloud Storage

### Pipeline Architecture

The specification generation workflow follows a five-stage multi-agent pipeline:

1. **TemplateAgent**: Parses PDF/Markdown templates and detects field types (text, paragraph, list, choice, table)

2. **ExtractionAgent**: Extracts data from connected repositories and data sources using a two-pass strategy with RAG-enhanced retrieval

3. **ValidationAgent**: Validates field completion and data quality

4. **MappingAgent**: Composites the final specification document deterministically without LLM hallucinations

5. **PipelineDetectionAgent**: Detects data pipelines and workflows in repositories

OrchestratorAgent coordinates all stages in a single pipeline.

## Prerequisites

### System Requirements

- Python 3.11 or higher
- Node.js 18.0 or higher
- npm 9.0 or higher

### Required Services

- LLM Provider: OpenAI, Anthropic
- GitHub Personal Access Token (for code analysis)

### Optional Data Sources

- PostgreSQL database
- BigQuery credentials
- Power BI Azure AD credentials
- Google Cloud Storage credentials

## Installation

### 1. Clone Repository

```bash
git clone https://github.com/ahmed493/Spec-Generator-Platform.git
cd Spec-Generator-Platform
```

### 2. Environment Configuration

Create .env file in project root:

```bash
# LLM Configuration
OPENAI_API_KEY=your_openai_api_key
# OR
ANTHROPIC_API_KEY=your_anthropic_api_key

# GitHub Integration
GITHUB_TOKEN=your_github_personal_access_token

# Database
DATABASE_URL=sqlite:///./spec_generator.db

# LLM Provider Selection
LLM_PROVIDER=openai

# Frontend Configuration
FRONTEND_URL=http://localhost:3000
VITE_API_URL=http://localhost:8000/api
```

### 3. Install Backend Dependencies

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Initialize Vector Store

```bash
python -c "from app.vectorstore import get_vector_manager; vm = get_vector_manager(); print('Vector store initialized')"
```

### 5. Install Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

## Running the Project

### Start Backend

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend available at: http://localhost:8000
API documentation: http://localhost:8000/docs

### Start Frontend

```bash
cd frontend
npm run dev
```

Frontend available at: http://localhost:3000

## Usage

### Typical Workflow

1. Create Project: Navigate to Projects page and create a new project

2. Connect Data Sources: Go to Connections page and configure GitHub and other data sources

3. Upload Template: In Pipeline page, upload PDF or Markdown template. System auto-detects fields

4. Extract Data: Select repositories and run extraction. Review and confirm extracted values

5. Generate Specification: Compose final specification from confirmed values

6. Export: Download as Markdown, JSON, or PDF, or publish to GitHub

## Project Structure

```
Spec-Generator-Platform/
├── app/                              # FastAPI backend
│   ├── main.py                       # FastAPI application setup
│   ├── db.py                         # SQLAlchemy session management
│   ├── models.py                     # ORM models
│   ├── config/
│   │   └── settings.py               # Configuration
│   ├── api/
│   │   └── routes.py                 # API endpoints
│   ├── agents/                       # Multi-agent LLM pipeline
│   │   ├── template_agent.py         # Template parsing and field detection
│   │   ├── extraction_agent.py       # Data extraction with RAG
│   │   ├── mapping_agent.py          # Specification composition
│   │   ├── validation_agent.py       # Field validation
│   │   ├── orchestrator_agent.py     # Pipeline coordination
│   │   ├── llm_client.py             # LLM provider wrapper
│   │   └── prompts/                  # LLM system prompts
│   ├── mcp_servers/                  # Data connectors
│   │   ├── github_server.py
│   │   ├── postgresql_server.py
│   │   ├── bigquery_server.py
│   │   ├── powerbi_server.py
│   │   └── gcs_server.py
│   └── vectorstore/                  # ChromaDB and embeddings
├── frontend/                         # React + Vite frontend
│   ├── package.json
│   ├── vite.config.js
│   ├── public/
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── api.js
│       ├── context/
│       │   └── ProjectContext.jsx    # Global state management
│       ├── components/
│       └── pages/
├── scripts/
│   └── compute_kpis.py               # Performance metrics script
├── requirements.txt
└── README.md
```

## Testing

### Manual Tests

```bash
# Test extraction pipeline
python test_extraction.py

# Test mapping pipeline
python run_mapping_test.py

# Measure performance metrics
python scripts/compute_kpis.py
```

### API Testing

Use Swagger UI at http://localhost:8000/docs to test all API endpoints.

## Configuration

### LLM Provider Selection

Set in .env:

```bash
# OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

# Anthropic
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...



### Database Configuration

Development (default):
```bash
DATABASE_URL=sqlite:///./spec_generator.db
```

Production:
```bash
DATABASE_URL=postgresql://user:password@host:5432/spec_generator
```

## Security Considerations

- Never commit .env file with real API keys
- Update CORS_ORIGINS in production
- Use PostgreSQL with encrypted connections in production
- Implement proper secrets management for API keys
- Enable authentication in production environment


