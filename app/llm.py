"""Configure DSPy to use a local, open-source model served by Ollama.

No API keys. No cloud calls. No cost. Everything runs on your machine.
DSPy reaches Ollama through LiteLLM using the `ollama_chat/<model>` id.
"""
from __future__ import annotations

from .config import settings

_configured = False
_error: str | None = None


def configure_lm() -> tuple[bool, str | None]:
    """Configure DSPy's global LM once. Returns (ok, error_message)."""
    global _configured, _error
    if _configured:
        return True, None
    try:
        import dspy

        lm = dspy.LM(
            model=settings.llm_model,
            api_base=settings.ollama_base_url,
            api_key="",          # Ollama needs no key
            temperature=0.3,
            max_tokens=settings.llm_max_tokens,
            num_ctx=settings.ollama_num_ctx,  # Ollama-specific; forwarded via LiteLLM
        )
        dspy.configure(lm=lm)
        _configured = True
        return True, None
    except Exception as exc:  # dspy not installed, or Ollama unreachable
        _error = (
            f"{type(exc).__name__}: {exc}. "
            "Install DSPy (`pip install dspy-ai`) and run Ollama "
            f"(`ollama pull {settings.llm_model.split('/')[-1]}`)."
        )
        return False, _error


def llm_status() -> dict:
    """Report whether the local LLM is reachable, for the UI banner."""
    ok, err = configure_lm()
    if not ok:
        return {"available": False, "model": settings.llm_model, "error": err}
    # Try a tiny generation to confirm Ollama is actually serving the model.
    try:
        import dspy

        dspy.settings.lm("ping")  # cheap round-trip
        return {"available": True, "model": settings.llm_model, "error": None}
    except Exception as exc:
        return {
            "available": False,
            "model": settings.llm_model,
            "error": (
                f"DSPy is installed but the model could not be reached: {exc}. "
                f"Is Ollama running at {settings.ollama_base_url}?"
            ),
        }
