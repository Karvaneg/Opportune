"""Tests du provisioning Ollama : inventaire, pull streamé, agrégation de progression (OPP-193)."""

import io
import urllib.request

import pytest

from app.ollama_provision import (
    OllamaUnreachable,
    PullAggregator,
    PullProgress,
    _get_json,
    list_models,
    model_present,
    model_with_tag,
    pull_model,
)

# Flux NDJSON réaliste d'``/api/pull`` (observé sur Ollama) : manifeste, une couche de poids
# qui progresse, puis la finalisation jusqu'à ``success``.
_PULL_EVENTS = [
    {"status": "pulling manifest"},
    {"status": "pulling abc", "digest": "sha256:abc", "total": 1000, "completed": 0},
    {"status": "pulling abc", "digest": "sha256:abc", "total": 1000, "completed": 500},
    {"status": "pulling abc", "digest": "sha256:abc", "total": 1000, "completed": 1000},
    {"status": "verifying sha256 digest"},
    {"status": "success"},
]


def test_aggregator_fraction_tracks_completed_over_total():
    aggregator = PullAggregator()

    aggregator.update({"status": "pulling abc", "digest": "sha256:abc", "total": 1000, "completed": 0})
    half = aggregator.update(
        {"status": "pulling abc", "digest": "sha256:abc", "total": 1000, "completed": 500}
    )

    assert half.fraction == 0.5


def test_aggregator_sums_across_layers():
    aggregator = PullAggregator()

    aggregator.update({"status": "pulling a", "digest": "a", "total": 800, "completed": 400})
    both = aggregator.update({"status": "pulling b", "digest": "b", "total": 200, "completed": 0})

    assert both.fraction == 0.4  # 400 / (800 + 200)


def test_aggregator_success_is_done_at_full():
    aggregator = PullAggregator()

    done = aggregator.update({"status": "success"})

    assert done.done is True
    assert done.fraction == 1.0


def test_aggregator_surfaces_error():
    aggregator = PullAggregator()

    failed = aggregator.update({"status": "error", "error": "disque plein"})

    assert failed.error == "disque plein"


def test_list_models_parses_tags():
    tags = {"models": [{"name": "ministral-3:3b"}, {"name": "llama3:8b"}]}

    names = list_models(transport=lambda url: tags)

    assert names == ["ministral-3:3b", "llama3:8b"]


def test_model_present_true_when_listed():
    tags = {"models": [{"name": "ministral-3:3b"}]}

    assert model_present("ministral-3:3b", transport=lambda url: tags) is True


def test_model_present_false_when_absent():
    assert model_present("ministral-3:3b", transport=lambda url: {"models": []}) is False


def test_pull_model_streams_progress_and_finishes_done():
    seen: list[float] = []

    result = pull_model(
        "ministral-3:3b",
        on_progress=lambda p: seen.append(p.fraction),
        transport=lambda url, payload: iter(_PULL_EVENTS),
    )

    assert result.done is True
    assert result.fraction == 1.0
    assert seen[-1] == 1.0
    assert 0.5 in seen


def test_pull_model_without_success_reports_error():
    truncated = [{"status": "pulling abc", "digest": "a", "total": 1000, "completed": 500}]

    result = pull_model("m", transport=lambda url, payload: iter(truncated))

    assert result.done is False
    assert result.error is not None


def test_pull_model_propagates_event_error():
    failing = [{"status": "error", "error": "quota"}]

    result = pull_model("m", transport=lambda url, payload: iter(failing))

    assert result.error == "quota"


def test_list_models_raises_when_unreachable():
    def refuse(url):
        raise OllamaUnreachable("connexion refusée")

    with pytest.raises(OllamaUnreachable):
        list_models(transport=refuse)


def test_get_json_maps_non_json_200_to_unreachable(monkeypatch):
    """Un service tiers occupe le port et répond 200 en texte (pas de JSON) : le décodage doit
    remonter en OllamaUnreachable, pas en JSONDecodeError brute (sinon status()/start() cassent).
    """

    class _FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(url, timeout=None):
        return _FakeResponse(b"Not Found")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(OllamaUnreachable):
        _get_json("http://127.0.0.1:11434/api/tags")


def test_model_present_matches_untagged_model_with_latest():
    inventory_listing_latest = lambda url: {"models": [{"name": "ministral-3:latest"}]}  # noqa: E731

    assert model_present("ministral-3", transport=inventory_listing_latest) is True


def test_model_present_does_not_match_another_tag():
    inventory_listing_other_tag = lambda url: {"models": [{"name": "ministral-3:8b"}]}  # noqa: E731

    assert model_present("ministral-3", transport=inventory_listing_other_tag) is False
    assert model_present("ministral-3:3b", transport=inventory_listing_other_tag) is False


def test_model_with_tag_adds_latest_only_when_tag_is_missing():
    model_without_tag = "ministral-3"
    model_with_explicit_tag = "ministral-3:3b"
    registry_with_port_and_no_tag = "registry.local:5000/team/custom"

    assert model_with_tag(model_without_tag) == "ministral-3:latest"
    assert model_with_tag(model_with_explicit_tag) == "ministral-3:3b"
    assert model_with_tag(registry_with_port_and_no_tag) == "registry.local:5000/team/custom:latest"
