"""
fetch_repo_files — GitHub REST API file fetcher for extraction.

Uses the git-tree API (single call for file list) then fetches individual
file blobs via GET /repos/{owner}/{repo}/contents/{path}.

Returns:
    {
        "python_files":   [{"path": str, "content": str}, ...],
        "sql_files":      [...],
        "yaml_files":     [...],
        "json_files":     [...],
        "notebook_files": [...],
        "code_files":     [...],   # PHP, Java, JS/TS, shell, etc.
    }
"""
import base64
import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Extension → category mapping
_EXT_MAP: dict[str, str] = {
    ".py":   "python_files",
    ".sql":  "sql_files",
    ".yaml": "yaml_files",
    ".yml":  "yaml_files",
    ".toml": "yaml_files",
    ".cfg":  "yaml_files",
    ".ini":  "yaml_files",
    ".json": "json_files",
    ".ipynb": "notebook_files",
    # Code (fallback bucket)
    ".php":  "code_files",
    ".java": "code_files",
    ".kt":   "code_files",
    ".scala": "code_files",
    ".go":   "code_files",
    ".cs":   "code_files",
    ".rs":   "code_files",
    ".rb":   "code_files",
    ".js":   "code_files",
    ".ts":   "code_files",
    ".mjs":  "code_files",
    ".sh":   "code_files",
    ".bash": "code_files",
    ".ps1":  "code_files",
    ".cpp":  "code_files",
    ".c":    "code_files",
    ".h":    "code_files",
    ".xml":  "code_files",
    ".tf":   "code_files",
}

_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".idea", "vendor", "target", ".mvn",
    "coverage", ".next", ".nuxt", "out",
}

# Per-category caps to avoid sending a 60 MB prompt to the LLM
_CAPS: dict[str, int] = {
    "python_files":   20,
    "sql_files":      15,
    "yaml_files":     15,
    "json_files":     10,
    "notebook_files": 5,
    "code_files":     30,
}

# Max chars of content per file (to stay within LLM context window)
_MAX_CONTENT_CHARS = 4000

# Max total files fetched regardless of category
_MAX_TOTAL_FILES = 80

# Seconds between requests — stay well under GitHub's 5000 req/hr primary limit
_REQUEST_DELAY = 0.05


def fetch_repo_files(
    owner: str,
    repo: str,
    token: str,
    branch: Optional[str] = None,
    *,
    max_total: int = _MAX_TOTAL_FILES,
    max_content_chars: int = _MAX_CONTENT_CHARS,
) -> dict[str, list[dict]]:
    """
    Fetch relevant file contents from a GitHub repository.

    Args:
        owner:  GitHub username / organisation.
        repo:   Repository name (without owner prefix).
        token:  GitHub personal access token.
        branch: Branch/ref to use; defaults to the repo's default branch.
        max_total: Hard cap on total files fetched.
        max_content_chars: Truncate each file's content to this many chars.

    Returns:
        Dict with keys: python_files, sql_files, yaml_files, json_files,
                        notebook_files, code_files — each a list of
                        {"path": str, "content": str}.
    """
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    base = "https://api.github.com"

    result: dict[str, list[dict]] = {k: [] for k in _CAPS}

    # ── 1. Resolve default branch if not provided ────────────────────────────
    if not branch:
        try:
            r = requests.get(f"{base}/repos/{owner}/{repo}", headers=headers, timeout=15)
            r.raise_for_status()
            branch = r.json().get("default_branch", "main")
        except Exception as exc:
            logger.warning("[fetch_repo_files] Could not resolve default branch: %s", exc)
            branch = "main"

    # ── 2. Fetch full recursive git tree (single API call) ───────────────────
    try:
        r = requests.get(
            f"{base}/repos/{owner}/{repo}/git/trees/{branch}",
            headers=headers,
            params={"recursive": "1"},
            timeout=30,
        )
        r.raise_for_status()
        tree_items = r.json().get("tree", [])
    except Exception as exc:
        logger.error("[fetch_repo_files] Failed to fetch git tree: %s", exc)
        return result

    # ── 3. Score and filter paths ────────────────────────────────────────────
    # Priority scoring: lower = more relevant to pipelines/ETL
    _PRIORITY_KEYWORDS = {
        "pipeline", "etl", "dag", "job", "import", "export", "command",
        "handler", "service", "worker", "migration", "fixture", "schedule",
        "transform", "load", "extract", "process", "sql", "query",
    }

    scored: list[tuple[int, int, str]] = []  # (score, size, path)
    for item in tree_items:
        if item.get("type") != "blob":
            continue
        path: str = item.get("path", "")
        path_lower = path.lower()
        parts = path_lower.split("/")

        if any(sd in parts for sd in _SKIP_DIRS):
            continue

        filename = parts[-1]
        dot_pos = filename.rfind(".")
        ext = filename[dot_pos:] if dot_pos >= 0 else ""

        if ext not in _EXT_MAP:
            continue

        has_keyword = any(kw in path_lower for kw in _PRIORITY_KEYWORDS)
        size = item.get("size", 9999) or 9999
        score = 0 if has_keyword else 1
        scored.append((score, size, path))

    scored.sort(key=lambda x: (x[0], x[1]))
    logger.info(
        "[fetch_repo_files] %s/%s@%s — tree:%d relevant:%d",
        owner, repo, branch, len(tree_items), len(scored),
    )

    # ── 4. Fetch file contents respecting per-category caps ──────────────────
    counts: dict[str, int] = {k: 0 for k in _CAPS}
    total_fetched = 0

    for _, _, path in scored:
        if total_fetched >= max_total:
            break

        filename = path.lower().split("/")[-1]
        dot_pos = filename.rfind(".")
        ext = filename[dot_pos:] if dot_pos >= 0 else ""
        category = _EXT_MAP.get(ext)
        if category is None:
            continue
        if counts[category] >= _CAPS[category]:
            continue

        try:
            time.sleep(_REQUEST_DELAY)
            r = requests.get(
                f"{base}/repos/{owner}/{repo}/contents/{path}",
                headers=headers,
                params={"ref": branch},
                timeout=15,
            )
            if r.status_code == 404:
                continue
            r.raise_for_status()
            data = r.json()
            raw_content = data.get("content", "")
            encoding = data.get("encoding", "base64")
            if encoding == "base64" and raw_content:
                content = base64.b64decode(raw_content).decode("utf-8", errors="replace")
            else:
                content = raw_content

            content = content[:max_content_chars]
            result[category].append({"path": path, "content": content})
            counts[category] += 1
            total_fetched += 1

        except Exception as exc:
            logger.debug("[fetch_repo_files] Skipped %s: %s", path, exc)
            continue

    summary = {k: len(v) for k, v in result.items() if v}
    logger.info("[fetch_repo_files] Done — fetched %d files total: %s", total_fetched, summary)
    return result


def merge_fetched_into_metadata(metadata: dict, fetched: dict) -> dict:
    """
    Merge fetch_repo_files() output into an existing repo_metadata dict.
    New files are appended; duplicates (same path) are skipped.
    """
    for key, new_files in fetched.items():
        existing = metadata.get(key, [])
        existing_paths = {f.get("path") for f in existing}
        added = 0
        for f in new_files:
            if f["path"] not in existing_paths:
                existing.append(f)
                existing_paths.add(f["path"])
                added += 1
        metadata[key] = existing
        if added:
            logger.info("[merge] +%d new %s (total %d)", added, key, len(existing))
    return metadata
