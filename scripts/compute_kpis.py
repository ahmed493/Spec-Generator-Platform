#!/usr/bin/env python3
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.agents.orchestrator_agent import OrchestratorAgent

IGNORE_DIRS = {'.git', 'venv', 'node_modules', '.cache', '.vite', '__pycache__', 'dist'}
CODE_EXTENSIONS = {'.js', '.jsx', '.ts', '.tsx', '.php', '.java', '.cs', '.go', '.rb', '.sh'}


def is_unfilled(value):
    if value is None:
        return True

    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return True
        if normalized == 'NOT_FOUND':
            return True
        if normalized == '[À compléter]':
            return True
        return False

    if isinstance(value, list):
        if len(value) == 0:
            return True
        if all(isinstance(el, str) and el.strip() == 'NOT_FOUND' for el in value):
            return True
        return False

    if isinstance(value, dict):
        return len(value) == 0

    return False


def build_repo_metadata(root: Path) -> dict:
    python_files = []
    yaml_files = []
    json_files = []
    sql_files = []
    notebook_files = []
    code_files = []
    structure_files = []

    for path in root.rglob('*'):
        if path.is_dir():
            if any(part in IGNORE_DIRS for part in path.parts):
                continue
            continue

        if any(part in IGNORE_DIRS for part in path.parts):
            continue

        structure_files.append(str(path.relative_to(root)).replace('\\', '/'))
        ext = path.suffix.lower()
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue

        item = {'path': str(path.relative_to(root)).replace('\\', '/'), 'content': text}
        if ext == '.py':
            python_files.append(item)
        elif ext in {'.yml', '.yaml'}:
            yaml_files.append(item)
        elif ext == '.json':
            json_files.append(item)
        elif ext == '.sql':
            sql_files.append(item)
        elif ext == '.ipynb':
            notebook_files.append(item)
        elif ext in CODE_EXTENSIONS:
            code_files.append(item)

    readme_path = root / 'README.md'
    readme_text = ''
    if readme_path.exists():
        readme_text = readme_path.read_text(encoding='utf-8', errors='replace')

    return {
        'repo_name': root.name,
        'owner': 'local',
        'description': 'Local spec-generator repository',
        'readme': readme_text,
        'languages': 'Python, JavaScript',
        'topics': 'spec-generation, pipeline detection',
        'structure': {'files': [{'path': p} for p in sorted(structure_files)]},
        'python_files': python_files,
        'yaml_files': yaml_files,
        'json_files': json_files,
        'sql_files': sql_files,
        'notebook_files': notebook_files,
        'code_files': code_files,
    }


def compute_fill_rate(fields, extracted_values):
    total = len(fields)
    if total == 0:
        return 0.0, 0, 0

    filled = 0
    for field in fields:
        fid = field.get('id')
        if fid is None:
            continue
        value = extracted_values.get(fid)
        if not is_unfilled(value):
            filled += 1

    return 100.0 * filled / total, filled, total


def main():
    parser = argparse.ArgumentParser(description='Compute fill rate and latency for spec generation.')
    parser.add_argument('--template', default='scripts/test_template.md', help='Path to the template file')
    parser.add_argument('--repo-root', default=str(ROOT), help='Path to the repository root')
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    template_path = Path(args.template).resolve()
    if not template_path.exists():
        raise FileNotFoundError(f'Template file not found: {template_path}')

    file_bytes = template_path.read_bytes()
    filename = template_path.name
    repo_metadata = build_repo_metadata(repo_root)
    agent = OrchestratorAgent()

    start = time.perf_counter()
    result = agent.generate(file_bytes, filename, repo_metadata)
    latency = time.perf_counter() - start

    fields = result.get('fields', []) or []
    extracted_values = result.get('extracted_values', {}) or {}
    fill_rate, filled, total = compute_fill_rate(fields, extracted_values)

    print(f'Fill rate: {fill_rate:.1f}%')
    print(f'Latency: {latency:.1f} s')
    print(f'Fill rate & $\\geq 85\\%$ & {fill_rate:.1f}\\% \\\\')
    print(f'End-to-end latency & $\\leq 60\\,s & {latency:.1f} s \\\\')

    print('\nFields total:', total)
    print('Fields filled:', filled)
    print('Validation report:\n', result.get('validation', {}).get('report', '<none>'))


if __name__ == '__main__':
    main()
