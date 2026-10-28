"""Tests de la configuration LLM / Ollama (OPP-073).

Aucun appel réseau : le transport est injecté (transport factice).
"""

import pytest

from app.llm import (
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_HOST,
    _env_int,
    build_generate_request,
    generate,
)


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


def test_build_request_omits_format_by_default():
    _, payload = build_generate_request("Bonjour")
    assert "format" not in payload  # non-régression : texte libre par défaut


def test_build_request_threads_format_schema():
    schema = {"type": "object", "required": ["title"]}
    _, payload = build_generate_request("Bonjour", fmt=schema)
    assert payload["format"] == schema


def test_build_request_accepts_json_string_format():
    _, payload = build_generate_request("Bonjour", fmt="json")
    assert payload["format"] == "json"


def test_build_request_omits_num_predict_by_default():
    _, payload = build_generate_request("Bonjour")
    assert "options" not in payload  # non-régression : aucune borne par défaut


def test_build_request_threads_num_predict():
    _, payload = build_generate_request("Bonjour", num_predict=256)
    assert payload["options"] == {"num_predict": 256}


def test_build_request_threads_temperature():
    # OPP-213 : la température est passée à Ollama via options.temperature (0 = déterministe).
    _, payload = build_generate_request("Bonjour", temperature=0.0)
    assert payload["options"] == {"temperature": 0.0}


def test_build_request_merges_num_predict_and_temperature():
    _, payload = build_generate_request("Bonjour", num_predict=256, temperature=0.2)
    assert payload["options"] == {"num_predict": 256, "temperature": 0.2}


def test_build_request_empty_prompt_raises():
    with pytest.raises(ValueError):
        build_generate_request("   ")


# --- _env_int : lecture tolérante d'un entier positif depuis l'env (OPP-154) ------
# Sert à DEFAULT_NUM_PREDICT (OLLAMA_NUM_PREDICT) ; tolérant par choix (jamais de raise).


def test_env_int_absent_uses_default(monkeypatch):
    monkeypatch.delenv("OLLAMA_NUM_PREDICT", raising=False)
    assert _env_int("OLLAMA_NUM_PREDICT", 2048) == 2048


def test_env_int_valid_value(monkeypatch):
    monkeypatch.setenv("OLLAMA_NUM_PREDICT", "512")
    assert _env_int("OLLAMA_NUM_PREDICT", 2048) == 512


@pytest.mark.parametrize("bad", ["", "   ", "abc", "0", "-5", "12.5"])
def test_env_int_invalid_or_non_positive_falls_back(monkeypatch, bad):
    # Vide, non entier, nul ou négatif → défaut (le paramètre de perf ne bloque pas le démarrage).
    monkeypatch.setenv("OLLAMA_NUM_PREDICT", bad)
    assert _env_int("OLLAMA_NUM_PREDICT", 2048) == 2048


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
