"""Tests for the minimal .env loader — in particular, that a hand-edited
file with a duplicate key resolves to the last line, not the first."""
import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import _load_dotenv  # noqa: E402

ENV_KEYS = ["LLM_MODEL", "HOST", "PORT", "VAULT_DIR", "SCHEMA_DIR",
            "OLLAMA_BASE_URL", "EMBEDDING_MODEL", "CHROMA_DIR",
            "CHUNK_SIZE", "MAX_CHUNKS"]


def _clean_env():
    for key in ENV_KEYS:
        os.environ.pop(key, None)


def test_last_duplicate_key_wins(tmp_path):
    _clean_env()
    try:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "LLM_MODEL=ollama_chat/llama3.1\n"
            "LLM_MODEL=ollama_chat/qwen2.5:3b\n"
        )
        _load_dotenv(env_file)
        assert os.environ["LLM_MODEL"] == "ollama_chat/qwen2.5:3b"
    finally:
        _clean_env()


def test_real_os_env_var_takes_priority_over_dotenv(tmp_path):
    _clean_env()
    try:
        os.environ["LLM_MODEL"] = "ollama_chat/from-shell"
        env_file = tmp_path / ".env"
        env_file.write_text("LLM_MODEL=ollama_chat/from-file\n")
        _load_dotenv(env_file)
        assert os.environ["LLM_MODEL"] == "ollama_chat/from-shell"
    finally:
        _clean_env()


def test_missing_file_is_a_noop(tmp_path):
    _clean_env()
    _load_dotenv(tmp_path / "does-not-exist.env")
    assert "LLM_MODEL" not in os.environ


def test_strips_quotes_and_whitespace(tmp_path):
    _clean_env()
    try:
        env_file = tmp_path / ".env"
        env_file.write_text('  LLM_MODEL = "ollama_chat/qwen2.5:3b"  \n')
        _load_dotenv(env_file)
        assert os.environ["LLM_MODEL"] == "ollama_chat/qwen2.5:3b"
    finally:
        _clean_env()
