"""Tests du contrat d'intégration LLM (OPP-079).

Aucun appel réseau : le transport est injecté (transport factice) pour
``OllamaLLMClient``, et ``MockLLMClient`` ne touche jamais le réseau.
"""

import urllib.error

import pytest

from app import llm
from app.llm_client import (
    LLMClient,
    LLMError,
    LLMResponse,
    LLMResponseError,
    LLMTimeoutError,
    MockLLMClient,
    OllamaLLMClient,
)


# --- Conformité au protocole -------------------------------------------------


def test_implementations_satisfy_protocol():
    assert isinstance(OllamaLLMClient(), LLMClient)
    assert isinstance(MockLLMClient(), LLMClient)


# --- OllamaLLMClient (implémentation réelle, transport injecté) ---------------


def test_ollama_generate_returns_structured_response():
    def fake_transport(url, payload):
        return {"response": "analyse simulée", "model": payload["model"], "done": True}

    client = OllamaLLMClient(transport=fake_transport)
    out = client.generate("Analyse cette offre")

    assert isinstance(out, LLMResponse)
    assert out.text == "analyse simulée"
    assert out.model == llm.DEFAULT_MODEL  # modèle par défaut (surchargé par env)
    assert out.raw["done"] is True  # le corps brut reste accessible


def test_ollama_propagates_model_and_host():
    seen = {}

    def fake_transport(url, payload):
        seen["url"] = url
        seen["model"] = payload["model"]
        return {"response": "ok"}

    client = OllamaLLMClient(
        model="ministral:8b", host="http://remote:1234", transport=fake_transport
    )
    client.generate("prompt")

    assert seen["url"] == "http://remote:1234/api/generate"
    assert seen["model"] == "ministral:8b"


def test_ollama_threads_format_into_payload():
    seen = {}

    def fake_transport(url, payload):
        seen["payload"] = payload
        return {"response": "ok"}

    schema = {"type": "object", "required": ["title"]}
    client = OllamaLLMClient(transport=fake_transport)
    client.generate("prompt", fmt=schema)
    assert seen["payload"]["format"] == schema


def test_ollama_without_format_omits_it():
    seen = {}

    def fake_transport(url, payload):
        seen["payload"] = payload
        return {"response": "ok"}

    OllamaLLMClient(transport=fake_transport).generate("prompt")
    assert "format" not in seen["payload"]  # non-régression : texte libre


def test_ollama_per_call_model_overrides_default():
    seen = {}

    def fake_transport(url, payload):
        seen["model"] = payload["model"]
        return {"response": "ok"}

    client = OllamaLLMClient(model="ministral", transport=fake_transport)
    client.generate("prompt", model="mistral-large")
    assert seen["model"] == "mistral-large"


def test_ollama_empty_prompt_raises_value_error():
    client = OllamaLLMClient(transport=lambda url, payload: {"response": "x"})
    with pytest.raises(ValueError):
        client.generate("   ")


def test_ollama_empty_response_string_is_valid():
    client = OllamaLLMClient(transport=lambda url, payload: {"response": ""})
    assert client.generate("prompt").text == ""


def test_ollama_missing_response_field_raises():
    client = OllamaLLMClient(transport=lambda url, payload: {"done": True})
    with pytest.raises(LLMResponseError):
        client.generate("prompt")


def test_ollama_timeout_is_typed():
    def timing_out(url, payload):
        raise TimeoutError("trop lent")

    client = OllamaLLMClient(transport=timing_out)
    with pytest.raises(LLMTimeoutError):
        client.generate("prompt")


def test_ollama_urlerror_timeout_is_mapped_to_timeout():
    def failing(url, payload):
        raise urllib.error.URLError(TimeoutError("timed out"))

    client = OllamaLLMClient(transport=failing)
    with pytest.raises(LLMTimeoutError):
        client.generate("prompt")


def test_ollama_network_error_is_wrapped():
    def failing(url, payload):
        raise urllib.error.URLError("connexion refusée")

    client = OllamaLLMClient(transport=failing)
    with pytest.raises(LLMError):
        client.generate("prompt")


# --- MockLLMClient (implémentation de test) ----------------------------------


def test_mock_replays_scripted_responses_in_order_and_records_calls():
    client = MockLLMClient(["première", "seconde"])

    assert client.generate("A").text == "première"
    assert client.generate("B", model="mistral").text == "seconde"
    assert [c["prompt"] for c in client.calls] == ["A", "B"]
    assert client.calls[1]["model"] == "mistral"


def test_mock_records_format_argument():
    client = MockLLMClient(["ok"])
    schema = {"type": "object"}
    client.generate("A", fmt=schema)
    assert client.calls[0]["fmt"] == schema


def test_mock_accepts_single_string():
    client = MockLLMClient("réponse unique")
    assert client.generate("A").text == "réponse unique"


def test_mock_accepts_full_response_objects():
    scripted = LLMResponse(text="t", model="m", raw={"done": True})
    client = MockLLMClient([scripted])
    assert client.generate("A") is scripted


def test_mock_raises_configured_error():
    client = MockLLMClient(error=LLMTimeoutError("boom"))
    with pytest.raises(LLMTimeoutError):
        client.generate("A")


def test_mock_exhausted_responses_raise():
    client = MockLLMClient([])
    with pytest.raises(LLMResponseError):
        client.generate("A")


def test_mock_empty_prompt_raises_value_error():
    client = MockLLMClient(["x"])
    with pytest.raises(ValueError):
        client.generate("")
