"""Tests de la configuration LLM / Ollama (OPP-073).

Aucun appel réseau : le transport est injecté (transport factice).
"""

import pytest

from app.llm import DEFAULT_MODEL, DEFAULT_OLLAMA_HOST, build_generate_request, generate


def test_build_request_defaults():
    url, payload = build_generate_request("Bonjour")
    assert url == f"{DEFAULT_OLLAMA_HOST}/api/generate"
    assert payload["model"] == DEFAULT_MODEL  # Ministral par défaut
    assert payload["prompt"] == "Bonjour"
    assert payload["stream"] is False


def test_build_request_overrides_and_trailing_slash():
    url, payload = build_generate_request("Salut", model="mistral", host="http://ollama:11434/")
    assert url == "http://ollama:11434/api/generate"  # slash final normalisé
    assert payload["model"] == "mistral"


def test_build_request_empty_prompt_raises():
    with pytest.raises(ValueError):
        build_generate_request("   ")


def test_generate_uses_injected_transport():
    captured = {}

    def fake_transport(url, payload):
        captured["url"] = url
        captured["payload"] = payload
        return {"response": "réponse simulée"}

    out = generate("Analyse cette offre", transport=fake_transport)
    assert out == "réponse simulée"
    assert captured["url"].endswith("/api/generate")
    assert captured["payload"]["prompt"] == "Analyse cette offre"


def test_generate_missing_response_field_returns_empty():
    assert generate("x", transport=lambda url, payload: {}) == ""


def test_generate_propagates_model_and_host():
    seen = {}

    def fake_transport(url, payload):
        seen["url"] = url
        seen["model"] = payload["model"]
        return {"response": "ok"}

    generate("prompt", model="ministral:8b", host="http://remote:1234", transport=fake_transport)
    assert seen["url"] == "http://remote:1234/api/generate"
    assert seen["model"] == "ministral:8b"
