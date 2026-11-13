from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


def _ollama_generate(prompt: str) -> str | None:
    """Try a local Ollama-compatible server without making the app depend on it."""
    host = os.environ.get("ANVESHAN_LLM_URL") or os.environ.get("OLLAMA_HOST")
    if not host:
        host = "http://127.0.0.1:11434"
    host = host.rstrip("/")
    model = os.environ.get("ANVESHAN_LLM_MODEL", "llama3.2:1b")
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 180},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{host}/api/generate",
        data=payload,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=2.5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
        return None
    text = str(data.get("response") or "").strip()
    return text or None


def generate_analyst_brief(prompt: str) -> tuple[str | None, dict]:
    text = _ollama_generate(prompt)
    if text:
        return text, {
            "available": True,
            "provider": "local Ollama-compatible endpoint",
            "model": os.environ.get("ANVESHAN_LLM_MODEL", "llama3.2:1b"),
        }
    return None, {
        "available": False,
        "provider": "deterministic offline analyst writer",
        "model": "rule-based fallback",
    }
