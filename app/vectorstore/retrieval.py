"""
Retrieval-Augmented Extraction (RAE)
Enhances the extraction agent with semantic search over template and repository content.
Provides context from the vector store to improve field extraction.
"""
from typing import Optional
from app.vectorstore import get_vector_manager
from app.agents.llm_client import BaseLLMClient, get_llm_client


RAE_SYSTEM_PROMPT = """Tu es un expert en analyse de code et data engineering spécialisé dans l'extraction d'informations.
Tu analyses le contenu de repositories et templates pour extraire des valeurs précises.
Tu utilises le contexte fourni par la recherche sémantique pour trouver les informations les plus pertinentes.
Réponds toujours en JSON valide uniquement, sans texte supplémentaire."""


RAE_PROMPT = """Tu dois extraire des informations à partir des métadonnées d'un repository et de résultats de recherche sémantique.

## Métadonnées du repository:
{metadata_summary}

## Contexte sémantique pertinent (templates similaires):
{template_context}

## Contexte sémantique pertinent (contenu de repository similaire):
{content_context}

## Champs à remplir:
{fields_description}

## Instructions:
- Pour chaque champ, fournis une valeur pertinente, concise et précise.
- Utilise d'abord le contexte sémantique pour trouver les informations.
- Adapte la longueur de la réponse au type du champ (text=court, paragraph=détaillé, list=liste à puces).
- Si l'information n'est pas disponible, indique "Non identifié".
- Réponds UNIQUEMENT avec un objet JSON valide où les clés sont les "id" des champs.

Format de réponse:
{{
  "field_id": "valeur extraite",
  ...
}}
"""


class RetrievalAugmentedExtraction:
    """
    Enhances extraction with semantic search over templates and repository content.
    Provides context to the LLM from vector store to improve extraction accuracy.
    """
    
    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self.llm = llm_client or get_llm_client()
        self.vector_manager = get_vector_manager()
    
    def extract_with_rae(
        self,
        repo_metadata: dict,
        fields: list[dict],
        project_id: str,
    ) -> dict[str, str]:
        """
        Extract field values with retrieval-augmented context.
        
        Args:
            repo_metadata: Repository metadata
            fields: List of fields to extract
            project_id: Project ID for vector store filtering
            
        Returns:
            Dict of {field_id: extracted_value}
        """
        field_ids = [f["id"] for f in fields]
        
        # Build queries for semantic search based on fields
        template_context = self._get_template_context(fields, project_id)
        content_context = self._get_content_context(fields, project_id, repo_metadata)
        
        # Prepare metadata summary
        metadata_summary = self._prepare_metadata_summary(repo_metadata)
        fields_description = self._format_fields(fields)
        
        # Build prompt with RAE context
        prompt = RAE_PROMPT.format(
            metadata_summary=metadata_summary,
            template_context=template_context,
            content_context=content_context,
            fields_description=fields_description,
        )
        
        # Generate with LLM using enhanced context
        raw = self.llm.generate(prompt, system_prompt=RAE_SYSTEM_PROMPT)
        return self._parse_json_response(raw, field_ids)
    
    def _get_template_context(self, fields: list[dict], project_id: str) -> str:
        """
        Search vector store for template examples similar to the fields we need to extract.
        """
        parts = []
        
        # Get a general overview of templates for this project
        try:
            templates = self.vector_manager.get_all_templates(project_id)
            if not templates:
                return "Aucun template n'a été trouvé dans la base de données."
            
            # For each field, search for similar templates
            for field in fields[:5]:  # Limit to first 5 fields to avoid too much context
                query = f"{field.get('label', '')} {field.get('description', '')}"
                results = self.vector_manager.search_templates(
                    query=query,
                    project_id=project_id,
                    top_k=2
                )
                
                if results:
                    parts.append(f"\n### Field: {field.get('label', field.get('id'))}")
                    for i, result in enumerate(results):
                        parts.append(f"  Exemple {i+1}: {result['content'][:300]}...")
            
            if not parts:
                parts.append("Aucun template similaire trouvé.")
        
        except Exception as e:
            parts.append(f"Erreur lors de la recherche de templates: {str(e)}")
        
        return "\n".join(parts)
    
    def _get_content_context(
        self,
        fields: list[dict],
        project_id: str,
        repo_metadata: dict
    ) -> str:
        """
        Search vector store for repository content similar to the fields we need to extract.
        """
        parts = []
        
        try:
            # Build search queries based on field descriptions
            queries = []
            for field in fields[:5]:  # Limit to first 5 fields
                label = field.get('label', '')
                description = field.get('description', '')
                if label or description:
                    queries.append(f"{label} {description}")
            
            # Search for relevant content
            seen_files = set()
            for query in queries:
                if not query.strip():
                    continue
                
                results = self.vector_manager.search_repository_content(
                    query=query,
                    project_id=project_id,
                    top_k=3
                )
                
                for result in results:
                    file_path = result['metadata'].get('file_path', 'unknown')
                    if file_path not in seen_files:
                        seen_files.add(file_path)
                        content_preview = result['content'][:200]
                        parts.append(f"  File `{file_path}`: {content_preview}...")
            
            if not parts:
                parts.append("Aucun contenu pertinent trouvé dans le repository.")
        
        except Exception as e:
            parts.append(f"Erreur lors de la recherche de contenu: {str(e)}")
        
        return "\n".join(parts) if parts else "Aucun contenu pertinent trouvé."
    
    def _prepare_metadata_summary(self, metadata: dict) -> str:
        """Prepare a summary of repository metadata."""
        parts = []
        parts.append(f"Nom du repo: {metadata.get('repo_name', 'N/A')}")
        parts.append(f"Owner: {metadata.get('owner', 'N/A')}")
        parts.append(f"Description: {metadata.get('description', 'N/A')}")
        parts.append(f"Langages: {metadata.get('languages', 'N/A')}")
        parts.append(f"Topics: {metadata.get('topics', 'N/A')}")
        
        if metadata.get("readme"):
            parts.append(f"\n## README:\n{metadata['readme'][:2000]}")
        
        return "\n".join(parts)
    
    def _format_fields(self, fields: list[dict]) -> str:
        """Format fields for the prompt."""
        lines = []
        for f in fields:
            parts = [f'- id="{f["id"]}" | label="{f.get("label", "")}"']
            if f.get("section"):
                parts.append(f'section="{f["section"]}"')
            if f.get("description"):
                parts.append(f'description="{f["description"]}"')
            if f.get("type"):
                parts.append(f'type={f["type"]}')
            lines.append(" | ".join(parts))
        return "\n".join(lines)
    
    def _parse_json_response(self, raw: str, field_ids: list[str]) -> dict[str, str]:
        """Parse JSON response with fallback."""
        import json
        raw = raw.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
        if raw.endswith("```"):
            raw = "\n".join(raw.split("\n")[:-1])
        raw = raw.strip()
        
        try:
            data = json.loads(raw)
            return {fid: str(data.get(fid, "Non identifié")) for fid in field_ids}
        except json.JSONDecodeError:
            return {fid: "Non identifié" for fid in field_ids}
