"""
Source RAG (Retrieval-Augmented Generation) for local source directories.

Indexes all source files in a given directory and provides keyword-based
search to return relevant code snippets. The approach mirrors the
github-rag.ts scoring: keyword hits in the file path score 3×, content
hits score 1× each (capped at 10 per keyword).
"""

import os
import re
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_FILE_SIZE = 200_000      # bytes — skip files larger than this
MAX_FILES = 20_000           # hard cap on number of indexed files
MAX_CONTEXT_CHARS = 8_000    # max total chars returned by search()
MAX_FILES_RETURNED = 5       # max files included in a single search result

PRIORITY_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".py", ".go", ".rs", ".java", ".c", ".cpp", ".h", ".hpp", ".cs",
    ".rb", ".php", ".swift", ".kt", ".scala", ".ex", ".exs",
    ".md", ".json", ".yaml", ".yml", ".toml", ".ini", ".sh", ".bash",
    ".sql", ".graphql", ".proto",
}

SKIP_PREFIXES = {
    "node_modules", ".git", "dist", "build", ".next", "coverage",
    "vendor", "__pycache__", "target", ".cargo", "pkg",
    "__snapshots__", ".cache", ".turbo", ".venv", "venv", "env",
    ".mypy_cache", ".pytest_cache", "htmlcov",
}

STOP_WORDS = {
    "the", "and", "for", "that", "this", "with", "are", "was", "not", "but",
    "from", "have", "has", "been", "will", "would", "could", "should", "may",
    "can", "its", "they", "them", "what", "when", "where", "how", "which",
    "any", "all", "more", "also", "into", "each", "some", "than", "then",
    "there", "these", "those", "just", "use", "used", "using", "make", "made",
    "get", "set", "let", "var", "new", "return", "type", "function", "class",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _should_skip(rel_path: str) -> bool:
    """Return True if any path component is in SKIP_PREFIXES."""
    parts = Path(rel_path).parts
    return any(p in SKIP_PREFIXES for p in parts)


def _extract_keywords(text: str) -> list[str]:
    text = re.sub(r"```[\s\S]*?```", " ", text)
    words = re.sub(r"[^\w\s]", " ", text.lower()).split()
    return [w for w in words if len(w) > 2 and w not in STOP_WORDS]


def _score_file(rel_path: str, content: str, keywords: list[str]) -> int:
    if not keywords:
        return 0
    score = 0
    path_lower = rel_path.lower()
    content_lower = content.lower()
    for kw in keywords:
        if kw in path_lower:
            score += 3
        count = 0
        pos = 0
        while count < 10:
            idx = content_lower.find(kw, pos)
            if idx == -1:
                break
            count += 1
            pos = idx + len(kw)
        score += count
    return score


# ---------------------------------------------------------------------------
# SourceRAG
# ---------------------------------------------------------------------------

class SourceRAG:
    """Keyword-based RAG over a local source directory."""

    def __init__(self, source_dir: str) -> None:
        self.source_dir = Path(source_dir).resolve()
        # rel_path -> content
        self._files: dict[str, str] = {}
        self._index()

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def _index(self) -> None:
        """Walk source_dir and load all eligible source files."""
        count = 0
        for root, dirs, files in os.walk(self.source_dir):
            # Prune skip dirs in-place so os.walk doesn't descend into them
            dirs[:] = [d for d in dirs if d not in SKIP_PREFIXES and not d.startswith(".")]

            for fname in files:
                if count >= MAX_FILES:
                    break
                full_path = Path(root) / fname
                try:
                    rel = str(full_path.relative_to(self.source_dir))
                except ValueError:
                    continue

                if _should_skip(rel):
                    continue

                ext = full_path.suffix.lower()
                if ext not in PRIORITY_EXTENSIONS:
                    continue

                try:
                    size = full_path.stat().st_size
                    if size > MAX_FILE_SIZE:
                        continue
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                    self._files[rel] = content
                    count += 1
                except OSError:
                    continue

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(self, query: str, max_files: int = MAX_FILES_RETURNED,
               max_chars: int = MAX_CONTEXT_CHARS) -> str:
        """
        Return a formatted string of the most relevant source files for query.
        Returns an empty string if nothing matches.
        """
        keywords = _extract_keywords(query)
        if not keywords:
            return ""

        scored = []
        for rel, content in self._files.items():
            s = _score_file(rel, content, keywords)
            if s > 0:
                scored.append((s, rel, content))

        if not scored:
            # Fall back to path listing
            relevant = [
                rel for rel in self._files
                if any(kw in rel.lower() for kw in keywords)
            ][:20]
            if not relevant:
                return ""
            lines = [f"## Source directory: {self.source_dir.name}", "",
                     "Relevant files (no content match):"]
            lines += [f"- {p}" for p in relevant]
            return "\n".join(lines) + "\n"

        scored.sort(key=lambda t: t[0], reverse=True)
        top = scored[:max_files]

        result = f"## Source directory: {self.source_dir.name}\n\n"
        chars_used = len(result)

        for _, rel, content in top:
            ext = Path(rel).suffix.lstrip(".")
            header = f"### {rel}\n```{ext}\n"
            footer = "\n```\n\n"
            available = max_chars - chars_used - len(header) - len(footer)
            if available < 50:
                break
            snippet = content[:available]
            result += header + snippet + footer
            chars_used += len(header) + len(snippet) + len(footer)

        return result

    def get_file(self, path: str) -> Optional[str]:
        """
        Return the content of a specific file (relative path from source_dir).
        Returns None if the file is not in the index.
        """
        # Normalise separators
        norm = path.replace("\\", "/").lstrip("/")
        # Try exact match first
        if norm in self._files:
            return self._files[norm]
        # Try suffix match (user may omit leading path components)
        for rel in self._files:
            if rel.replace("\\", "/").endswith(norm):
                return self._files[rel]
        return None

    def list_files(self) -> list[str]:
        """Return all indexed file paths (relative to source_dir)."""
        return sorted(self._files.keys())

    @property
    def indexed_count(self) -> int:
        return len(self._files)
