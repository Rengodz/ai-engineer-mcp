from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import (
    clear_documents,
    get_db_path,
    init_db,
    insert_documents,
)

SOURCE_DIR = PROJECT_ROOT / "ai-engineering-hub"
EXTENSIONS = {".py", ".md", ".txt"}
IGNORED_DIRS = {
    ".git",
    ".github",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".ipynb_checkpoints",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "dist",
    "build",
    "site-packages",
}


def iter_source_files(source_dir: Path):
    for path in source_dir.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        rel_parts = path.relative_to(source_dir).parts
        if any(
            part.startswith(".") or part in IGNORED_DIRS
            for part in rel_parts[:-1]
        ):
            continue
        if path.suffix.lower() in EXTENSIONS:
            yield path


def build_title(path: Path) -> str:
    return path.stem.replace("_", " ").replace("-", " ").strip() or path.name


def read_document(path: Path) -> str | None:
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    if not content.strip():
        return None
    return content


def collect_documents(source_dir: Path) -> list[tuple[str, str, str]]:
    documents: list[tuple[str, str, str]] = []
    for path in sorted(iter_source_files(source_dir)):
        content = read_document(path)
        if content is None:
            continue
        relative_path = path.relative_to(PROJECT_ROOT).as_posix()
        documents.append((build_title(path), relative_path, content))
    return documents


def index(source_dir: Path = SOURCE_DIR) -> tuple[int, Path]:
    if not source_dir.is_dir():
        raise SystemExit(
            f"Dossier source introuvable : {source_dir}\n"
            "Clonez le dépôt avec :\n"
            "  git clone --depth 1 "
            "https://github.com/patchy631/ai-engineering-hub.git"
        )

    documents = collect_documents(source_dir)
    db_path = get_db_path()
    conn = init_db()
    try:
        clear_documents(conn)
        inserted = insert_documents(documents, conn)
        conn.execute("INSERT INTO documents_fts(documents_fts) VALUES ('optimize')")
        conn.commit()
    finally:
        conn.close()

    return inserted, db_path


def main() -> None:
    inserted, db_path = index()
    print(f"Indexation terminée : {inserted} documents")
    print(f"Base de données : {db_path}")
    print(f"Source : {SOURCE_DIR}")


if __name__ == "__main__":
    main()
