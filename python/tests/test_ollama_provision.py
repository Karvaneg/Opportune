"""Tests du provisioning Ollama : inventaire, pull streamé, agrégation de progression (OPP-193)."""

import pytest

from app.ollama_provision import (
    OllamaUnreachable,
    PullAggregator,
    PullProgress,
    list_models,
    model_present,
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
