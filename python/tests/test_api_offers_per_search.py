"""Offres propres à chaque recherche, bout en bout sur l'API assemblée (OPP-186).

``assemble_api`` câble les vrais dépôts SQLite (base temporaire) ; seul l'intake LLM est
remplacé par un faux qui persiste une offre fixe : ni Ollama ni réseau. On vérifie qu'une
offre ajoutée dans une recherche n'apparaît ni dans le catalogue ni dans les compteurs d'une
autre recherche, et qu'une recherche neuve part sans offre.
"""

import pytest

from api.server import assemble_api, build_local_auth
from app import offer_intake_service
from app.candidate_registry import CandidateRegistry
from app.db import connect
from app.offer import Offer


def _fake_intake(raw_text, *, source, client, store, url=""):
    offer = Offer(
        id=f"offre-{raw_text}",
        title=raw_text,
        company="Acme",
        location="Paris",
        skills=["Python"],
        seniority="Senior",
        contract_type="CDI",
        summary="s",
        attention_points=[],
        source=source,
        url=url,
        raw_text=raw_text,
    )
    store.save(offer)
    return offer


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(offer_intake_service, "intake_offer", _fake_intake)
    conn = connect(str(tmp_path / "opportune.db"))
    registry = CandidateRegistry(conn)
    registry.add("cand-a", label="Recherche A")
    registry.add("cand-b", label="Recherche B")
    yield assemble_api(
        conn,
        build_local_auth(registry.list_ids),
        searches=registry,
        settings_dir=tmp_path / "settings",
    )
    conn.close()


def _catalog_ids(api, candidate_id):
    body = api.dispatch("GET", f"/offers?candidate_id={candidate_id}", None, None).body
    return [item["id"] for item in body["items"]], body["total"]


def _offers_total(api, candidate_id):
    return api.dispatch("GET", f"/candidates/{candidate_id}/stats", None, None).body[
        "offres_total"
    ]


def test_offer_added_to_a_search_is_invisible_to_the_others(api):
    resp = api.dispatch("POST", "/offers", {"text": "dev", "candidate_id": "cand-a"}, None)

    assert resp.status == 201
    assert _catalog_ids(api, "cand-a") == (["offre-dev"], 1)
    assert _catalog_ids(api, "cand-b") == ([], 0)
    assert _offers_total(api, "cand-a") == 1
    assert _offers_total(api, "cand-b") == 0


def test_same_offer_added_to_two_searches_is_stored_once(api):
    api.dispatch("POST", "/offers", {"text": "dev", "candidate_id": "cand-a"}, None)
    api.dispatch("POST", "/offers", {"text": "dev", "candidate_id": "cand-b"}, None)

    all_offers = api.dispatch("GET", "/offers", None, None).body

    assert _catalog_ids(api, "cand-b") == (["offre-dev"], 1)
    assert all_offers["total"] == 1


def test_new_search_starts_without_offers(api):
    api.dispatch("POST", "/offers", {"text": "dev", "candidate_id": "cand-a"}, None)
    created = api.dispatch("POST", "/searches", {"label": "Neuve"}, None).body

    assert _catalog_ids(api, created["id"]) == ([], 0)
    assert _offers_total(api, created["id"]) == 0


def test_offer_already_known_is_dated_from_its_entry_into_the_search(api):
    # Revue OPP-186 : une vieille offre de A, ajoutée aujourd'hui à B, est récente pour B dans le
    # catalogue comme dans le journal d'activité (sinon le filtre des 5 dernières l'écarte).
    api.dispatch("POST", "/offers", {"text": "dev", "candidate_id": "cand-a"}, None)
    old = "2020-01-01T00:00:00+00:00"
    api.conn.execute("UPDATE offers SET created_at = ?", (old,))
    api.conn.execute("UPDATE candidate_offers SET created_at = ?", (old,))
    api.conn.commit()

    api.dispatch("POST", "/offers", {"text": "dev", "candidate_id": "cand-b"}, None)
    catalog_b = api.dispatch("GET", "/offers?candidate_id=cand-b", None, None).body
    activity_b = api.dispatch("GET", "/candidates/cand-b/activity", None, None).body
    catalog_a = api.dispatch("GET", "/offers?candidate_id=cand-a", None, None).body

    assert catalog_b["items"][0]["created_at"] > old
    assert [e["at"] > old for e in activity_b["items"] if e["type"] == "offer"] == [True]
    assert catalog_a["items"][0]["created_at"] == old


def test_collect_job_tells_which_search_receives_its_offers(api):
    started = api.dispatch(
        "POST", "/collect", {"source": "rss", "candidate_id": "cand-b"}, None
    ).body

    job = api.dispatch("GET", f"/collect/{started['job_id']}", None, None).body

    assert job["candidate_id"] == "cand-b"
