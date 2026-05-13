"""
ExtractionAgent Ã¢â‚¬â€ Strict Source-Only Extraction
Strategy:
  Pass 1  Ã¢â‚¬â€œ Section-batched extraction (10 fields/call, context scoped to relevant files)
  Pass 2  Ã¢â‚¬â€œ Batched retry for NOT_FOUND fields (up to 5/call, broader file context)
  NO synthesis pass Ã¢â‚¬â€ synthesis was the main source of hallucination
"""
import json
import logging
import re
import requests
from typing import Optional
from app.agents.llm_client import get_llm_client, BaseLLMClient
from app.agents.prompts.extraction_prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    RETRY_SYSTEM_PROMPT,
    BATCH_EXTRACTION_PROMPT,
    RETRY_BATCH_PROMPT,
)

logger = logging.getLogger(__name__)


# Section/field keyword -> preferred file extensions
_SECTION_EXT_MAP = [
    (
        ["source", "table", "schema", "query", "data", "lineage", "field", "column"],
        [".sql"],
    ),
    (
        [
            "transformation", "processing", "etl", "pipeline", "orchestration",
            "script", "job", "command", "service", "handler", "mapping",
        ],
        [".py", ".php", ".java", ".kt", ".scala", ".rb", ".go"],
    ),
    (
        ["config", "parameter", "deployment", "airflow", "dbt", "schedule", "trigger"],
        [".yaml", ".yml", ".toml", ".cfg", ".ini"],
    ),
    (
        ["analysis", "exploration", "visualization", "notebook"],
        [".ipynb"],
    ),
]

_ALL_CODE_EXTENSIONS = [
    ".py", ".sql", ".php", ".java", ".kt", ".scala", ".rb", ".go",
    ".cs", ".ts", ".js", ".yaml", ".yml", ".toml", ".cfg", ".ini",
    ".xml", ".sh", ".ipynb",
]


def _format_fetched_files(files: list) -> str:
    """Format a list of fetched file dicts into a prompt-ready string."""
    parts = []
    for f in files:
        path = f.get("path", "")
        content = f.get("content", "")
        fn = path.lower()
        if fn.endswith(".py"):
            fence = "python"
        elif fn.endswith(".sql"):
            fence = "sql"
        elif fn.endswith((".yaml", ".yml")):
            fence = "yaml"
        elif fn.endswith(".json"):
            fence = "json"
        elif fn.endswith(".php"):
            fence = "php"
        elif fn.endswith((".ts", ".js")):
            fence = "typescript"
        elif fn.endswith(".java"):
            fence = "java"
        else:
            fence = ""
        if fence:
            parts.append(f"### {path}\n```{fence}\n{content}\n```")
        else:
            parts.append(f"### {path}\n{content}")
    return "\n\n".join(parts)


class GitHubMCPFetcher:
    """On-demand file fetcher backed by GitHubMCPServer.

    Wraps the existing GitHubMCPServer to provide targeted, lazy file loading
    for extraction, avoiding the pre-load budget problem.
    """

    _SKIP_DIRS = {
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        "dist", "build", ".idea", "vendor", "target", ".mvn",
        "coverage", ".next", ".nuxt", "out",
    }
    _PRIORITY_KEYWORDS = {
        # generic ETL
        "pipeline", "etl", "dag", "job", "import", "export", "command",
        "handler", "service", "worker", "migration", "fixture", "schedule",
        "transform", "load", "extract", "process", "query", "mapper",
        "mapping", "reader", "writer", "loader",
        # SQL / database
        "select", "from", "join", "where", "group by", "order by",
        "insert", "update", "delete", "table", "column", "schema",
        "database", "connexion", "connection", "doctrine", "dbal",
        # domain / dunning
        "dunning", "unpaid", "b2c", "b2b", "report", "reporting",
        "invoice", "facture", "relance", "recouvrement", "impaye",
        "customer", "client", "contract", "contrat",
        "sage", "silvertool", "silvertools",
        "csv", "excel", "fputcsv", "fgetcsv",
    }
    _MAX_CONTENT_CHARS = 6000
    # Budget used inside _smart_truncate — larger to capture SQL-heavy methods
    _SMART_BUDGET = 24000

    def __init__(self, mcp_client, owner: str, repo: str):
        self._mcp = mcp_client   # GitHubMCPServer instance
        self.owner = owner
        self.repo = repo
        self._branch: Optional[str] = None
        self._tree: Optional[list] = None
        self._content_cache: dict = {}  # path -> content

    def _headers(self) -> dict:
        return {
            "Authorization": f"token {self._mcp.token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def _resolve_branch(self) -> str:
        if self._branch:
            return self._branch
        try:
            r = requests.get(
                f"https://api.github.com/repos/{self.owner}/{self.repo}",
                headers=self._headers(),
                timeout=10,
            )
            r.raise_for_status()
            self._branch = r.json().get("default_branch", "main")
        except Exception as exc:
            logger.warning("[GitHubMCPFetcher] branch resolve failed: %s", exc)
            self._branch = "main"
        return self._branch

    def get_file_tree(self) -> list:
        """Returns all file paths via a single git-tree API call (cached)."""
        if self._tree is not None:
            return self._tree
        branch = self._resolve_branch()
        try:
            r = requests.get(
                f"https://api.github.com/repos/{self.owner}/{self.repo}/git/trees/{branch}",
                headers=self._headers(),
                params={"recursive": "1"},
                timeout=30,
            )
            r.raise_for_status()
            items = r.json().get("tree", [])
            paths = []
            for item in items:
                if item.get("type") != "blob":
                    continue
                path: str = item.get("path", "")
                parts = path.lower().split("/")
                if any(sd in parts for sd in self._SKIP_DIRS):
                    continue
                paths.append(path)
            self._tree = paths
            logger.info(
                "[GitHubMCPFetcher] tree: %d files in %s/%s",
                len(paths), self.owner, self.repo,
            )
        except Exception as exc:
            logger.warning("[GitHubMCPFetcher] git-tree failed: %s", exc)
            self._tree = []
        return self._tree

    def get_file_content(self, path: str) -> str:
        """Fetches a single file by path (cached)."""
        if path in self._content_cache:
            return self._content_cache[path]
        results = self.get_files_by_paths([path])
        content = results[0]["content"] if results else ""
        self._content_cache[path] = content
        return content

    def _fetch_full_raw(self, path: str) -> str:
        """Fetches the complete raw content of a file from GitHub (no char limit)."""
        import base64 as _b64
        branch = self._resolve_branch()
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/contents/{path}"
        try:
            r = requests.get(url, headers=self._headers(), params={"ref": branch}, timeout=20)
            r.raise_for_status()
            data = r.json()
            raw = data.get("content", "")
            if data.get("encoding") == "base64":
                return _b64.b64decode(raw.replace("\n", "")).decode("utf-8", errors="replace")
            return raw
        except Exception as exc:
            logger.warning("[GitHubMCPFetcher] full fetch failed %s: %s", path, exc)
            return ""

    def _smart_truncate(self, path: str, content: str) -> str:
        """For large PHP/Python files, extract the most relevant sections instead of
        blindly taking the first N chars.  Keeps up to _MAX_CONTENT_CHARS total.
        Strategy: find all public/private function definitions, score by keyword
        relevance, and concatenate the top ones until the budget is exhausted.
        Falls back to simple head truncation for non-code or small files.
        """
        if len(content) <= self._SMART_BUDGET:
            return content

        ext = path.rsplit(".", 1)[-1].lower()
        if ext not in ("php", "py", "java", "ts", "js"):
            return content[: self._SMART_BUDGET]

        import re as _re
        # Split on PHP/Python function boundaries
        if ext == "php":
            pattern = _re.compile(
                r"(?=(?:public|protected|private|static|\s)+function\s+\w+)",
                _re.MULTILINE,
            )
        else:
            pattern = _re.compile(r"(?=\s*(?:async\s+)?def\s+\w+)", _re.MULTILINE)

        parts = pattern.split(content)
        if len(parts) <= 1:
            return content[: self._SMART_BUDGET]

        # Score each function block.
        # Function-NAME matches get 5x the weight of body matches so that
        # a method like getB2CUnpaidInternalData ranks above large generic ones.
        def _score_block(block: str) -> int:
            bl = block.lower()
            body_score = sum(10 for kw in self._PRIORITY_KEYWORDS if kw in bl)
            name_match = _re.search(r"function\s+(\w+)", block[:150])
            if name_match:
                fn_name = name_match.group(1).lower()
                body_score += sum(50 for kw in self._PRIORITY_KEYWORDS if kw in fn_name)
            return body_score

        scored = sorted(
            [(i, p, _score_block(p)) for i, p in enumerate(parts)],
            key=lambda x: (-x[2], x[0]),  # high score first, then original order
        )

        budget = self._SMART_BUDGET
        # Always include the class header (first block, usually namespace + class def)
        selected = []
        header = parts[0][:2000]
        selected.append((0, header))
        budget -= len(header)

        for orig_idx, block, _sc in scored:
            if orig_idx == 0:
                continue
            # Cap individual blocks at 4000 chars so one huge method
            # doesn't consume the entire budget
            chunk = block[: min(len(block), 4000)]
            if budget - len(chunk) < 0:
                break
            selected.append((orig_idx, chunk))
            budget -= len(chunk)

        selected.sort(key=lambda x: x[0])
        result = "\n".join(b for _, b in selected)
        logger.debug(
            "[GitHubMCPFetcher] smart_truncate %s: %d→%d chars (%d blocks)",
            path.split("/")[-1], len(content), len(result), len(selected),
        )
        return result

    def get_files_by_paths(self, paths: list) -> list:
        """Fetches multiple files, skipping already-cached ones.
        For files larger than _MAX_CONTENT_CHARS, fetches the full content and
        applies smart truncation to keep the most relevant function blocks.
        """
        to_fetch = [p for p in paths if p not in self._content_cache]
        if to_fetch:
            # First pass: standard fetch (fast, covers most files)
            fetched = self._mcp.fetch_files_by_paths(
                owner=self.owner,
                repo_name=self.repo,
                paths=to_fetch,
                branch=self._branch,
                max_chars=self._MAX_CONTENT_CHARS,
            )
            fetched_set = {f["path"] for f in fetched}
            for f in fetched:
                content = f.get("content", "")
                # If content hit the limit exactly, the file is likely truncated —
                # re-fetch the full file and apply smart truncation
                if len(content) >= self._MAX_CONTENT_CHARS - 10:
                    full = self._fetch_full_raw(f["path"])
                    if full:
                        content = self._smart_truncate(f["path"], full)
                self._content_cache[f["path"]] = content
            # Paths that failed the first pass (404 etc.) get empty string
            for p in to_fetch:
                if p not in fetched_set and p not in self._content_cache:
                    self._content_cache[p] = ""
        result = []
        for p in paths:
            c = self._content_cache.get(p)
            if c is not None:
                result.append({"path": p, "content": c})
        return result

    def get_files_by_extension(
        self,
        extensions: list,
        max_files: int = 10,
        priority_paths: Optional[list] = None,
    ) -> list:
        """Fetches up to max_files files matching the given extensions.

        Pipeline evidence paths are fetched first; remaining slots are filled
        by keyword-scored tree paths.
        """
        tree = self.get_file_tree()
        ext_set = {
            e.lower() if e.startswith(".") else f".{e.lower()}"
            for e in extensions
        }
        priority_lower = {(p or "").lower() for p in (priority_paths or [])}

        scored = []
        for path in tree:
            path_lower = path.lower()
            filename = path_lower.split("/")[-1]
            dot = filename.rfind(".")
            ext = filename[dot:] if dot >= 0 else ""
            if ext not in ext_set:
                continue
            if path_lower in priority_lower or any(
                ev and ev in path_lower for ev in priority_lower
            ):
                score = 0
            elif any(kw in path_lower for kw in self._PRIORITY_KEYWORDS):
                score = 1
            else:
                score = 2
            scored.append((score, path))

        scored.sort(key=lambda x: x[0])
        paths_to_fetch = [p for _, p in scored[:max_files]]
        if not paths_to_fetch:
            return []
        return self.get_files_by_paths(paths_to_fetch)

    def get_bundle_sibling_files(self, evidence_paths: list, max_files: int = 15) -> list:
        """Fetches Service/Repository/Entity/etc. files from the same bundle as evidence.

        Priority (highest first):
          30 - Service|Repository|Entity|Manager|Helper file with matching name keywords
          20 - Service|Repository|Entity|Manager|Helper file (any name) in same bundle
          10 - Other files in same bundle with name keywords (e.g. SQL migration)
           5 - Other files in same bundle, different dir from evidence
           1 - Name-keyword match anywhere in repo
          -1 - Skipped: same immediate directory as evidence (Commands delegate, not define)
        """
        if not evidence_paths:
            return []
        tree = self.get_file_tree()
        _CODE_EXTS = {
            ".php", ".py", ".java", ".kt", ".scala", ".rb", ".go", ".cs",
            ".ts", ".js", ".sql", ".sh",
        }
        # Subdirs that contain actual business logic (not orchestration)
        _LOGIC_DIRS = {"service", "services", "repository", "repositories",
                       "entity", "entities", "manager", "managers",
                       "helper", "helpers", "handler", "handlers",
                       "transformer", "transformers", "provider", "providers"}

        import re as _re

        # Derive bundle dir, evidence immediate dir, and name keywords per evidence path
        bundle_dirs: list = []   # (bundle_dir_lower, evidence_leaf_dir_lower, name_keywords)
        for ev_path in evidence_paths:
            parts = ev_path.replace("\\", "/").split("/")
            # Find deepest *Bundle/*Module/*Domain in path
            bundle_idx = None
            for i, part in enumerate(parts):
                pl = part.lower()
                if pl.endswith(("bundle", "module", "domain", "service")):
                    bundle_idx = i
            bundle_dir = "/".join(parts[:bundle_idx + 1]).lower() if bundle_idx is not None else None
            # Immediate parent dir of evidence file
            leaf_dir = "/".join(parts[:-1]).lower() if len(parts) > 1 else None
            # Name keywords from evidence file stem (CamelCase split, ≥4 chars)
            stem = parts[-1].rsplit(".", 1)[0]
            name_kws = {w.lower() for w in _re.findall(r"[A-Z][a-z]+|[a-z]{4,}", stem) if len(w) >= 4}
            bundle_dirs.append((bundle_dir, leaf_dir, name_kws))

        scored: list = []
        seen: set = set()
        for path in tree:
            path_lower = path.lower()
            fn = path_lower.split("/")[-1]
            dot = fn.rfind(".")
            ext = fn[dot:] if dot >= 0 else ""
            if ext not in _CODE_EXTS:
                continue

            # Path parts for subdir detection
            path_parts = path_lower.split("/")
            path_subdirs = {p for p in path_parts[:-1]}

            best = None
            for bundle_dir, leaf_dir, name_kws in bundle_dirs:
                in_bundle = bundle_dir and path_lower.startswith(bundle_dir + "/")
                in_leaf = leaf_dir and path_lower.startswith(leaf_dir + "/")
                in_logic = bool(path_subdirs & _LOGIC_DIRS)
                has_kw = bool(name_kws) and any(kw in fn for kw in name_kws)

                if in_leaf:
                    # Same Command dir as evidence — deprioritize
                    score = -1
                elif in_bundle and in_logic and has_kw:
                    score = 30
                elif in_bundle and in_logic:
                    score = 20
                elif in_bundle and has_kw:
                    score = 10
                elif in_bundle:
                    score = 5
                elif any(kw in path_lower for kw in name_kws):
                    score = 1
                else:
                    score = 0

                if best is None or score > best:
                    best = score

            if best is not None and best > 0 and path not in seen:
                seen.add(path)
                scored.append((-best, path))  # negate: higher score sorts first

        scored.sort(key=lambda x: x[0])
        paths_to_fetch = [p for _, p in scored[:max_files]]
        if not paths_to_fetch:
            return []
        logger.info(
            "[GitHubMCPFetcher] bundle siblings: %d files | top: %s",
            len(paths_to_fetch), paths_to_fetch[:5],
        )
        return self.get_files_by_paths(paths_to_fetch)

    def trace_php_imports(self, evidence_paths: list, max_files: int = 15) -> list:
        """Reads evidence files and resolves their PHP/Python import statements to real repo paths.

        For a PHP file with:
          use Ve\\DunningBundle\\Service\\DunningReportService;
        converts to:
          src/Ve/DunningBundle/Service/DunningReportService.php
        then finds the best match in the repo tree.
        """
        import re as _re
        tree = self.get_file_tree()
        tree_lower = [p.lower() for p in tree]

        # Build lookup: lowercased-filename-without-ext -> full path
        name_to_paths: dict = {}
        for path in tree:
            fn = path.split("/")[-1]
            dot = fn.rfind(".")
            stem = fn[:dot].lower() if dot >= 0 else fn.lower()
            name_to_paths.setdefault(stem, []).append(path)

        resolved: list = []
        seen: set = set()

        # Ensure evidence files are fetched first (needed to read imports)
        ev_files = self.get_files_by_paths(evidence_paths)

        for ev_file in ev_files:
            content = ev_file.get("content", "")
            if not content:
                continue

            # PHP: use Ns\Sub\ClassName; or use Ns\Sub\ClassName as Alias;
            php_uses = _re.findall(
                r"^\s*use\s+([\w\\]+)(?:\s+as\s+\w+)?\s*;",
                content, _re.MULTILINE,
            )
            # Python: from module.sub import Class / import module.sub
            py_imports = _re.findall(
                r"^\s*(?:from|import)\s+([\w.]+)",
                content, _re.MULTILINE,
            )

            candidates: list = []
            for ns in php_uses + py_imports:
                # Convert namespace to path candidates
                # PHP: Ve\Bundle\Service\ClassName -> src/Ve/Bundle/Service/ClassName.php
                parts = ns.replace("\\", "/").replace(".", "/").split("/")
                class_name = parts[-1].lower()

                # Try exact path match (namespace -> relative path)
                for ext in (".php", ".py", ".java", ".ts", ".js"):
                    candidate_suffix = "/".join(parts).lower() + ext
                    for i, tl in enumerate(tree_lower):
                        if tl.endswith(candidate_suffix) and tree[i] not in seen:
                            candidates.append(tree[i])
                            break

                # Fallback: filename match — only if unambiguous (single match)
                if class_name in name_to_paths and len(name_to_paths[class_name]) == 1:
                    p = name_to_paths[class_name][0]
                    if p not in seen:
                        candidates.append(p)

            for p in candidates:
                if p not in seen and len(resolved) < max_files:
                    seen.add(p)
                    resolved.append(p)

        if not resolved:
            return []

        logger.info(
            "[GitHubMCPFetcher] traced imports: %d files | top: %s",
            len(resolved), resolved[:5],
        )
        return self.get_files_by_paths(resolved)

    def find_files_by_keywords(self, keywords: list, max_files: int = 10) -> list:
        """Searches the file tree for code files whose paths contain any of the given keywords.

        Prioritises Service/Repository/Entity files over Command/Controller files.
        """
        import re as _re
        tree = self.get_file_tree()
        # Filter to meaningful keywords (len > 2, not generic suffixes)
        _GENERIC = {"command", "controller", "abstract", "base", "handler",
                    "listener", "subscriber", "interface", "exception", "helper"}
        kws = [k.lower() for k in keywords if len(k) > 2 and k.lower() not in _GENERIC]
        if not kws:
            return []

        _CODE_EXTS = (".php", ".py", ".java", ".ts", ".js", ".sql")

        def _score(path: str) -> int:
            pl = path.lower()
            if not any(pl.endswith(e) for e in _CODE_EXTS):
                return -1
            if not any(kw in pl for kw in kws):
                return -1
            s = 0
            if "/service/" in pl or "/repository/" in pl or "/entity/" in pl:
                s += 10
            elif "/command/" in pl or "/controller/" in pl:
                s += 1
            else:
                s += 5
            # Bonus: multiple keywords match
            s += sum(1 for kw in kws if kw in pl)
            return s

        scored = [(p, _score(p)) for p in tree]
        matched = sorted(
            [(p, sc) for p, sc in scored if sc >= 0],
            key=lambda x: x[1], reverse=True,
        )[:max_files]

        if not matched:
            return []

        paths = [p for p, _ in matched]
        fetched = self.get_files_by_paths(paths)
        logger.info(
            "[GitHubMCPFetcher] keyword search (%s): %d files | top: %s",
            kws, len(fetched), [f["path"] for f in fetched[:5]],
        )
        return fetched

    @property
    def unique_extensions(self) -> list:
        """Unique file extensions present in the tree (for debug logging)."""
        tree = self.get_file_tree()
        exts: set = set()
        for path in tree:
            fn = path.split("/")[-1].lower()
            dot = fn.rfind(".")
            if dot >= 0:
                exts.add(fn[dot:])
        return sorted(exts)

    @property
    def primary_extensions(self) -> list:
        """Top code extensions by file count — used as baseline for extraction."""
        _CODE_EXTS = {
            ".py", ".php", ".java", ".kt", ".scala", ".rb", ".go", ".cs",
            ".ts", ".js", ".sql", ".sh",
        }
        tree = self.get_file_tree()
        counts: dict = {}
        for path in tree:
            fn = path.split("/")[-1].lower()
            dot = fn.rfind(".")
            if dot >= 0:
                ext = fn[dot:]
                if ext in _CODE_EXTS:
                    counts[ext] = counts.get(ext, 0) + 1
        if not counts:
            return [".py"]
        return sorted(counts, key=lambda e: -counts[e])[:3]


class ExtractionAgent:
    """Two-pass strict extraction: section-batched Ã¢â€ â€™ batched retry for NOT_FOUND fields."""

    BATCH_SIZE  = 10   # fields per LLM call in pass 1
    RETRY_SIZE  = 5    # NOT_FOUND fields batched per retry call
    MAX_RETRIES = 15   # cap total fields retried to bound worst-case latency

    # Regex catching all common "not found" variants (EN + FR)
    _NOT_FOUND_RE = re.compile(
        r"^\s*(not[_\s]?found|non[_\s]?trouv[ée]?|non\s+identifi[ée].*|absent.*sources?|"
        r"introuvable|n/?a|aucun.*trouv|no\s+information|information\s+not\s+available|"
        r"not\s+available|not\s+present|not\s+specified|not\s+mentioned)\s*$",
        re.IGNORECASE,
    )

    def __init__(self, llm_client: Optional[BaseLLMClient] = None, mcp_client=None):
        self.llm = llm_client or get_llm_client()
        self.mcp_client = mcp_client

    # Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
    # Public API
    # Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

    def extract(self, repo_metadata: dict, fields: list) -> dict:
        """Two-pass strict extraction: section-batched then batched retry for NOT_FOUND fields."""
        if not fields:
            return {}

        pipeline_context = self._build_pipeline_context(repo_metadata)
        base_metadata = self._build_base_metadata(repo_metadata)

        # Collect pipeline evidence file paths
        sp = repo_metadata.get("selected_pipeline") or {}
        evidence_paths = list({
            p for p in (
                sp.get("source_files", [])
                + list((sp.get("explainability") or {}).get("evidence_files", []))
            )
        })

        # Build on-demand fetcher when a GitHub MCP client is available
        owner = repo_metadata.get("owner", "")
        repo_name = repo_metadata.get("repo_name", "")
        fetcher = None
        if self.mcp_client and owner and repo_name:
            try:
                fetcher = GitHubMCPFetcher(self.mcp_client, owner, repo_name)
                tree = fetcher.get_file_tree()
                logger.info("[ExtractionAgent] Repo: %s/%s", owner, repo_name)
                logger.info("[ExtractionAgent] File tree: %d files", len(tree))
                logger.info("[ExtractionAgent] Extensions found: %s", fetcher.unique_extensions)
            except Exception as exc:
                logger.warning(
                    "[ExtractionAgent] Failed to build fetcher: %s -- falling back to pre-loaded content",
                    exc,
                )
                fetcher = None

        # Build pre-loaded file index for fallback path (no MCP client)
        file_index = None
        if fetcher is None:
            file_index = self._build_file_index(repo_metadata)
            pipeline_evidence = {p.lower() for p in evidence_paths}
            if pipeline_evidence:
                def _evidence_key(f: dict) -> int:
                    return 0 if any(ev in f.get("path", "").lower() for ev in pipeline_evidence) else 1
                for ftype in file_index:
                    file_index[ftype] = sorted(file_index[ftype], key=_evidence_key)
            for ftype, files in file_index.items():
                if not files:
                    logger.warning("[ExtractionAgent] fallback %s: 0 files", ftype)
                else:
                    preview = (files[0].get("content", "") or "")[:200].replace("\n", " ")
                    logger.info(
                        "[ExtractionAgent] fallback %s: %d files | [0] '%s' preview: %s",
                        ftype, len(files), files[0].get("path", "?"), preview,
                    )

        logger.info(
            "[ExtractionAgent] pipeline_context len=%d fields=%d evidence=%d fetcher=%s",
            len(pipeline_context), len(fields), len(evidence_paths), fetcher is not None,
        )

        # Pass 1: section-batched extraction
        extracted: dict = {}
        for section_name, section_fields in self._group_by_section(fields).items():
            for i in range(0, len(section_fields), self.BATCH_SIZE):
                batch = section_fields[i:i + self.BATCH_SIZE]
                if fetcher is not None:
                    relevant = self._pick_and_fetch_relevant_files(
                        section_name, batch, fetcher, evidence_paths
                    )
                else:
                    relevant = self._pick_relevant_files(section_name, batch, file_index)
                extracted.update(
                    self._run_batch(section_name, batch, pipeline_context, base_metadata, relevant)
                )

        for f in fields:
            if f["id"] not in extracted:
                extracted[f["id"]] = "NOT_FOUND"

        # Pass 2: batched retry for NOT_FOUND fields
        not_found_fields = [
            f for f in fields if self._is_not_found(extracted.get(f["id"], ""))
        ][:self.MAX_RETRIES]
        if not_found_fields:
            if fetcher is not None:
                all_files_text = self._build_all_files_text_from_fetcher(fetcher, evidence_paths)
            else:
                all_files_text = self._build_all_files_text(file_index)
            for i in range(0, len(not_found_fields), self.RETRY_SIZE):
                retry_batch = not_found_fields[i:i + self.RETRY_SIZE]
                for fid, val in self._run_retry_batch(
                    retry_batch, pipeline_context, all_files_text
                ).items():
                    extracted[fid] = val if (val and not self._is_not_found(val)) else "NOT_FOUND"

        return extracted
    def _group_by_section(self, fields: list[dict]) -> dict[str, list[dict]]:
        groups: dict[str, list[dict]] = {}
        for f in fields:
            sec = f.get("section", "General") or "General"
            groups.setdefault(sec, []).append(f)
        return groups

    def _run_batch(self, section_name: str, batch: list[dict],
                   pipeline_context: str, base_metadata: str,
                   relevant_files: str) -> dict[str, str]:
        fields_desc = self._format_fields(batch)
        prompt = BATCH_EXTRACTION_PROMPT.format(
            pipeline_context=pipeline_context,
            relevant_files=relevant_files or "No specific files identified for this section.",
            base_metadata=base_metadata,
            section_name=section_name,
            fields_description=fields_desc,
        )
        raw = self.llm.generate(prompt, system_prompt=EXTRACTION_SYSTEM_PROMPT)
        field_ids = [f["id"] for f in batch]
        return self._parse_json_response(raw, field_ids)

    # Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
    # Pass 2 helpers
    # Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

    def _is_not_found(self, value: str) -> bool:
        if not value or not value.strip():
            return True
        return bool(self._NOT_FOUND_RE.match(value.strip()))

    def _run_retry_batch(self, fields: list[dict], pipeline_context: str,
                         all_files_text: str) -> dict[str, str]:
        fields_desc = self._format_fields(fields)
        prompt = RETRY_BATCH_PROMPT.format(
            pipeline_context=pipeline_context,
            fields_description=fields_desc,
            all_relevant_files=all_files_text[:40000],
        )
        raw = self.llm.generate(prompt, system_prompt=RETRY_SYSTEM_PROMPT)
        field_ids = [f["id"] for f in fields]
        return self._parse_json_response(raw, field_ids)

    # ── Context builders ────────────────────────────────────────────────────
    # Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

    def _build_pipeline_context(self, metadata: dict) -> str:
        parts = []
        ctx = metadata.get("datasource_context", "")
        if ctx:
            parts.append(ctx[:3000])
        sp = metadata.get("selected_pipeline")
        if sp:
            parts.append(
                f"Pipeline: {sp.get('name', '')}\n"
                f"Type: {sp.get('type', '')}\n"
                f"Description: {sp.get('description', '')}\n"
                f"Source files: {sp.get('source_files', [])}\n"
                f"Source tables: {sp.get('source_tables', [])}\n"
                f"Technologies: {sp.get('technologies', [])}"
            )
        if parts:
            return "\n\n".join(parts)
        desc = metadata.get("description", "")
        if desc:
            return desc[:2000]
        return "Global repository analysis — no specific pipeline provided."

    def _build_base_metadata(self, metadata: dict) -> str:
        parts = [
            f"Repo: {metadata.get('repo_name', 'N/A')}",
            f"Owner: {metadata.get('owner', 'N/A')}",
            f"Description: {metadata.get('description', 'N/A')}",
            f"Languages: {metadata.get('languages', 'N/A')}",
            f"Topics: {metadata.get('topics', 'N/A')}",
        ]
        if metadata.get("readme"):
            parts.append(f"\n## README:\n{metadata['readme'][:4000]}")
        if metadata.get("structure"):
            files = [f["path"] for f in metadata["structure"].get("files", [])]
            parts.append(f"\n## Files ({len(files)}):\n{json.dumps(files[:120], ensure_ascii=False)}")
        return "\n".join(parts)

    def _build_file_index(self, metadata: dict) -> dict[str, list[dict]]:
        return {
            "sql":      metadata.get("sql_files", []),
            "python":   metadata.get("python_files", []),
            "yaml":     metadata.get("yaml_files", []),
            "json":     metadata.get("json_files", []),
            "notebook": metadata.get("notebook_files", []),
            "code":     metadata.get("code_files", []),  # PHP, Java, JS/TS, etc.
        }

    def _build_all_files_text(self, file_index: dict) -> str:
        parts = []
        limits = {"sql": 5000, "python": 5000, "yaml": 2000, "json": 2000, "notebook": 3000, "code": 4000}
        labels = {"sql": "SQL", "python": "Python", "yaml": "YAML", "json": "JSON", "notebook": "Notebook", "code": "Code"}
        for ftype, files in file_index.items():
            for f in files[:12]:  # increased from 6 to 12 — evidence files sorted first
                lim = limits.get(ftype, 3000)
                parts.append(f"### [{labels[ftype]}] {f.get('path','')}\n{f.get('content','')[:lim]}")
        return "\n\n".join(parts)

    def _pick_and_fetch_relevant_files(
        self,
        section_name: str,
        fields: list,
        fetcher: "GitHubMCPFetcher",
        evidence_paths: list,
    ) -> str:
        """Fetches relevant files live for a batch of fields.

        Priority order:
          1. Evidence files themselves
          2. Files imported/used by the evidence files (import tracing)
          3. Bundle sibling logic files (Service/Repository/Entity in same bundle)
          4. Keyword/extension-scored files to fill remaining slots
        """
        seen: set = set()
        result: list = []

        def _add(files):
            for f in files:
                if f["path"] not in seen and len(result) < 20:
                    seen.add(f["path"])
                    result.append(f)

        # Step 1: evidence files directly
        if evidence_paths:
            _add(fetcher.get_files_by_paths(evidence_paths))

        # Step 2: keyword-based discovery from evidence file names
        # e.g. DunningB2cUnpaidInternalReportCommand -> [dunning, b2c, unpaid, report]
        if evidence_paths and len(result) < 15:
            import re as _re
            _STOPWORDS = {"command", "controller", "abstract", "base", "handler",
                          "listener", "subscriber", "interface", "exception",
                          "internal", "create", "update", "delete", "import",
                          "export", "sync", "get", "set", "process"}
            kw_set: set = set()
            for ep in evidence_paths:
                stem = ep.split("/")[-1].rsplit(".", 1)[0]
                parts = _re.sub(r"([A-Z])", r" \1", stem).split()
                for p in parts:
                    token = p.lower()
                    if token not in _STOPWORDS and len(token) > 2:
                        kw_set.add(token)
            if kw_set:
                _add(fetcher.find_files_by_keywords(list(kw_set), max_files=10))

        # Step 3: trace imports from evidence files (Service/Repository classes used)
        if evidence_paths and len(result) < 15:
            _add(fetcher.trace_php_imports(evidence_paths, max_files=8))

        # Step 4: bundle sibling logic files (Service/Repository/Entity)
        if evidence_paths and len(result) < 15:
            _add(fetcher.get_bundle_sibling_files(evidence_paths, max_files=10))

        # Step 5: fill remaining slots with extension-scored files
        if len(result) < 12:
            text = " ".join([
                section_name or "",
                *[f.get("label", "") for f in fields],
                *[f.get("description", "") for f in fields],
            ]).lower()
            selected_exts: set = set(fetcher.primary_extensions)
            selected_exts.add(".sql")
            for keywords, exts in _SECTION_EXT_MAP:
                if any(kw in text for kw in keywords):
                    selected_exts.update(exts)
            remaining = max(6, 12 - len(result))
            _add(fetcher.get_files_by_extension(
                extensions=list(selected_exts),
                max_files=remaining + 5,
                priority_paths=evidence_paths,
            ))

        # Step 6: last resort — any code files
        if not result:
            _add(fetcher.get_files_by_extension(
                extensions=_ALL_CODE_EXTENSIONS,
                max_files=10,
                priority_paths=evidence_paths,
            ))

        logger.info(
            "[ExtractionAgent] section='%s' fetched %d files | paths: %s",
            section_name, len(result), [f["path"] for f in result],
        )
        return _format_fetched_files(result)

    def _build_all_files_text_from_fetcher(
        self,
        fetcher: "GitHubMCPFetcher",
        evidence_paths: list,
    ) -> str:
        """Fetches a broad set of files for the Pass 2 retry context."""
        seen: set = set()
        result: list = []

        def _add(files):
            for f in files:
                if f["path"] not in seen:
                    seen.add(f["path"])
                    result.append(f)

        # Always include evidence files and their bundle siblings first
        if evidence_paths:
            _add(fetcher.get_files_by_paths(evidence_paths))
            _add(fetcher.get_bundle_sibling_files(evidence_paths, max_files=15))

        # Fill remaining with broad extension sweep
        _add(fetcher.get_files_by_extension(
            extensions=_ALL_CODE_EXTENSIONS,
            max_files=20,
            priority_paths=evidence_paths,
        ))
        return _format_fetched_files(result)[:40_000]

    def _pick_relevant_files(self, section_name: str, fields: list,
                              file_index: dict) -> str:
        # Always include all file types - no keyword heuristics that cause misses
        limits = {"sql": 5000, "python": 5000, "yaml": 2000, "json": 2000, "notebook": 3000, "code": 4000}
        fences = {"sql": "sql", "python": "python", "yaml": "yaml", "json": "json", "notebook": "", "code": ""}
        labels = {"sql": "SQL", "python": "Python", "yaml": "YAML", "json": "JSON", "notebook": "Notebook", "code": "Code"}
        caps   = {"sql": 4, "python": 4, "yaml": 3, "json": 3, "notebook": 2, "code": 4}

        parts = []
        for ftype, files in file_index.items():
            fence = fences[ftype]
            lim   = limits[ftype]
            cap   = caps[ftype]
            for f in files[:cap]:
                content = f.get("content", "")[:lim]
                if fence:
                    parts.append(f"### [{labels[ftype]}] {f.get('path','')}\n```{fence}\n{content}\n```")
                else:
                    parts.append(f"### [{labels[ftype]}] {f.get('path','')}\n{content}")

        return "\n\n".join(parts) if parts else ""

    def _format_fields(self, fields: list[dict]) -> str:
        lines = []
        for f in fields:
            parts = [f'- id="{f["id"]}" | label="{f.get("label","")}"']
            if f.get("section"):
                parts.append(f'section="{f["section"]}"')
            if f.get("description"):
                parts.append(f'description="{f["description"]}"')
            if f.get("type"):
                parts.append(f'type={f["type"]}')
            if f.get("options"):
                parts.append(f'options={f["options"]}')
            lines.append(" | ".join(parts))
        return "\n".join(lines)

    def _parse_json_response(self, raw: str, field_ids: list[str]) -> dict[str, str]:
        raw = raw.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()
        brace = raw.find("{")
        if brace > 0:
            raw = raw[brace:]
        last_brace = raw.rfind("}")
        if last_brace >= 0:
            raw = raw[:last_brace + 1]
        raw = re.sub(r",\s*([\}\]])", r"\1", raw)
        try:
            data = json.loads(raw)
            result = {}
            for fid in field_ids:
                if fid not in data:
                    continue
                v = data[fid]
                if isinstance(v, (list, dict)):
                    result[fid] = json.dumps(v, ensure_ascii=False)
                else:
                    result[fid] = str(v)
            return result
        except json.JSONDecodeError:
            return {}

    def _prepare_metadata_summary(self, metadata: dict) -> str:
        return self._build_base_metadata(metadata)