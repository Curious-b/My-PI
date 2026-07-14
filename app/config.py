"""Central configuration, sourced from environment variables (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so we don't require an extra dependency."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
_load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8000"))

    vault_dir: Path = PROJECT_ROOT / os.getenv("VAULT_DIR", "vault")

    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    llm_model: str = os.getenv("LLM_MODEL", "ollama_chat/llama3.1")

    embedding_model: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    chroma_dir: Path = PROJECT_ROOT / os.getenv("CHROMA_DIR", ".chroma")


settings = Settings()
