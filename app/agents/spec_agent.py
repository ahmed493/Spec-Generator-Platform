"""
Spec Generator Agent
Uses LLM to analyze repository metadata and generate specifications
"""
from typing import Optional
from app.agents.llm_client import get_llm_client, BaseLLMClient


SYSTEM_PROMPT = """Tu es un expert en documentation technique et data engineering.
Tu analyses des repositories de code et génères des spécifications techniques et fonctionnelles complètes.
Tu dois identifier:
- La couche de données (Bronze/Silver/Gold)
- Les sources et destinations de données
- Les transformations appliquées
- Le data lineage
- Les technologies utilisées

Réponds toujours en français et de manière structurée."""


SPEC_GENERATION_PROMPT = """Analyse les métadonnées suivantes d'un repository et génère une spécification complète.

## Métadonnées du repository:
{metadata}

## Template de spécification à suivre:

# Spécification: {repo_name}

## 1. Vue d'ensemble
### 1.1 Description du projet
[Description basée sur le README et le code]

### 1.2 Couche de données
- **Type de couche**: [Bronze/Silver/Gold]
- **Objectif**: [Objectif de cette couche]

## 2. Sources de données
### 2.1 Sources d'entrée
[Liste des sources d'entrée identifiées dans le code]

### 2.2 Destinations de sortie
[Liste des destinations identifiées]

## 3. Schéma de données
### 3.1 Tables/Fichiers
[Tables ou fichiers manipulés]

### 3.2 Champs clés
[Champs importants identifiés]

## 4. Transformations
### 4.1 Processus ETL
[Description des transformations]

### 4.2 Règles métier
[Règles métier identifiées dans le code]

## 5. Data Lineage
[Diagramme de flux de données en ASCII]

## 6. Dépendances
### 6.1 Dépendances upstream
[Ce dont ce repo dépend]

### 6.2 Dépendances downstream
[Ce qui dépend de ce repo]

## 7. Détails techniques
### 7.1 Technologies utilisées
[Liste des technologies]

### 7.2 Configuration
[Configurations importantes]

---
Génère maintenant la spécification complète en analysant le code fourni.
"""



# --- Chat history support ---
import threading
_chat_history_store = {}
_chat_history_lock = threading.Lock()

class SpecAgent:
    """Agent for generating specifications from repository metadata and handling chat with history"""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self.llm = llm_client or get_llm_client()

    def generate_spec(self, repo_metadata: dict) -> str:
        # ...existing code...
        metadata_summary = self._prepare_metadata_summary(repo_metadata)
        prompt = SPEC_GENERATION_PROMPT.format(
            metadata=metadata_summary,
            repo_name=repo_metadata.get("repo_name", "Unknown")
        )
        spec = self.llm.generate(prompt, system_prompt=SYSTEM_PROMPT)
        return spec

    def _prepare_metadata_summary(self, metadata: dict) -> str:
        # ...existing code...
        summary_parts = []
        summary_parts.append(f"Repository: {metadata.get('repo_name')}")
        summary_parts.append(f"Owner: {metadata.get('owner')}")
        summary_parts.append(f"Description: {metadata.get('description')}")
        summary_parts.append(f"Languages: {metadata.get('languages')}")
        summary_parts.append(f"Topics: {metadata.get('topics')}")
        if metadata.get("readme"):
            readme = metadata["readme"][:2000]
            summary_parts.append(f"\n## README:\n{readme}")
        if metadata.get("structure"):
            files = metadata["structure"].get("files", [])
            file_list = [f["path"] for f in files[:30]]
            summary_parts.append(f"\n## Structure:\n{file_list}")
        if metadata.get("sql_files"):
            summary_parts.append(f"\n## SQL Files ({len(metadata['sql_files'])}):")
            for sql in metadata["sql_files"][:5]:
                content = sql.get("content", "")[:1000]
                summary_parts.append(f"\n### {sql['path']}:\n```sql\n{content}\n```")
        if metadata.get("python_files"):
            summary_parts.append(f"\n## Python Files ({len(metadata['python_files'])}):")
            for py in metadata["python_files"][:5]:
                content = py.get("content", "")[:1500]
                summary_parts.append(f"\n### {py['path']}:\n```python\n{content}\n```")
        return "\n".join(summary_parts)

    def chat(self, question: str, user_id: str, repo_name: str = None, context: str = "") -> dict:
        """Answer questions about specifications or data contracts, with chat history support"""
        key = (user_id, repo_name or "global")
        with _chat_history_lock:
            history = _chat_history_store.get(key, [])
        # Build context from history
        history_context = ""
        for turn in history[-10:]:
            history_context += f"Utilisateur: {turn['question']}\nBot: {turn['answer']}\n"
        prompt = f"""Contexte de la spécification:
{context}

Historique du chat:
{history_context}

Question de l'utilisateur:
{question}

Réponds de manière claire et concise en français."""
        answer = self.llm.generate(prompt, system_prompt=SYSTEM_PROMPT)
        # Save to history
        with _chat_history_lock:
            history = _chat_history_store.get(key, [])
            history.append({"question": question, "answer": answer})
            _chat_history_store[key] = history[-20:]  # Keep last 20
        return {"answer": answer, "history": history[-10:]}
