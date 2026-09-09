"""Tests de l'adaptateur gateway Discord — parties pures (OPP-125).

On teste le seam **sans réseau** : le ``decide`` réel en process (mapping verbe → statut +
persistance de la décision) et le routage résilient d'un payload d'interaction. La coquille
async (connexion gateway) est ``pragma: no cover`` — la logique risquée est déjà couverte.
"""

import pytest

from app.db import connect
from app.decision import create_decision, decision_id
from app.decision_store import DecisionStore
from app.discord_authz import ReviewerAllowlist
from app.discord_review import encode_custom_id

from hermes.discord_gateway import (
    build_decider,
    build_gateway_decider,
    process_interaction,
)

RID = "cand-1:off-1"
REVIEWER_ID = "discord-user-1"
ALLOWLIST = ReviewerAllowlist(frozenset({REVIEWER_ID}))


def _click(verb: str, *, user_id: str = REVIEWER_ID) -> dict:
    return {
        "data": {"custom_id": encode_custom_id(verb, RID)},
        "member": {"user": {"id": user_id}},
    }


# --- build_decider (decide réel, en process) ---------------------------------


class _SpyOrchestrator:
    def __init__(self):
        self.calls = []

    def record_human_decision(self, recommendation_id, status, *, comment=None):
        self.calls.append((recommendation_id, status, comment))
        return ("decision", recommendation_id, status)


@pytest.mark.parametrize(
    "verb,status",
    [("approve", "approved"), ("reject", "rejected"), ("defer", "deferred")],
)
def test_build_decider_maps_verb_to_status(verb, status):
    spy = _SpyOrchestrator()
    decide = build_decider(spy)

    decide(RID, verb, None)

    assert spy.calls == [(RID, status, None)]


def test_build_decider_rejects_unknown_verb():
    decide = build_decider(_SpyOrchestrator())
    with pytest.raises(ValueError):
        decide(RID, "explode", None)


# --- process_interaction (routage résilient) ---------------------------------


def test_process_interaction_authorized_records_and_confirms():
    calls = []
    decide = lambda rid, verb, comment: calls.append((rid, verb, comment))  # noqa: E731

    response = process_interaction(_click("approve"), decide=decide, allowlist=ALLOWLIST)

    assert calls == [(RID, "approve", None)]
    assert response["data"]["flags"] == 64
    assert "approuvé" in response["data"]["content"]


def test_process_interaction_unauthorized_does_not_decide():
    def decide(*a):
        raise AssertionError("aucune décision pour un cliqueur non autorisé")

    response = process_interaction(
        _click("approve", user_id="intrus"), decide=decide, allowlist=ALLOWLIST
    )

    assert "autorisé" in response["data"]["content"]


def test_process_interaction_unrecognized_returns_response_without_raising():
    def decide(*a):
        raise AssertionError("decide ne doit pas être appelé")

    # custom_id étranger : handle_interaction lèverait InteractionError ; le seam la rattrape.
    interaction = {"data": {"custom_id": "other:x:y"}, "member": {"user": {"id": REVIEWER_ID}}}
    response = process_interaction(interaction, decide=decide, allowlist=ALLOWLIST)

    assert response["type"] == 4
    assert response["data"]["flags"] == 64
    assert "reconnue" in response["data"]["content"]


def test_process_interaction_swallows_decide_failure():
    # decide qui échoue (dossier introuvable, erreur de persistance…) : le seam doit
    # renvoyer une réponse éphémère plutôt que de laisser l'exception tomber la boucle.
    def decide(*a):
        raise RuntimeError("boum côté persistance")

    response = process_interaction(_click("approve"), decide=decide, allowlist=ALLOWLIST)

    assert response["type"] == 4
    assert response["data"]["flags"] == 64
    assert "impossible" in response["data"]["content"]


def test_process_interaction_logs_decide_failure(caplog):
    # L'échec réel est avalé côté boucle, mais tracé (traceback) pour le debug.
    def decide(*a):
        raise RuntimeError("boum côté persistance")

    with caplog.at_level("ERROR", logger="hermes.discord_gateway"):
        process_interaction(_click("approve"), decide=decide, allowlist=ALLOWLIST)

    assert any(r.levelname == "ERROR" for r in caplog.records)
    assert "boum côté persistance" in caplog.text  # la cause d'origine est capturée


def test_process_interaction_unknown_recommendation_does_not_raise():
    # Carte périmée : la décision n'existe plus en base → UnknownDecisionError, rattrapée.
    conn = connect(":memory:")
    decide = build_gateway_decider(conn)

    response = process_interaction(_click("approve"), decide=decide, allowlist=ALLOWLIST)

    assert "impossible" in response["data"]["content"]
    conn.close()


# --- build_gateway_decider (câblage en process, bout en bout) -----------------


def test_build_gateway_decider_persists_the_decision():
    conn = connect(":memory:")
    decisions = DecisionStore(conn)
    # Une décision pending préexiste (comme après un run push).
    decisions.save(create_decision(
        candidate_id="cand-1", offer_id="off-1", action="postuler",
        score=90, justification="Bon match",
    ))

    decide = build_gateway_decider(conn)
    decide(decision_id("cand-1", "off-1"), "approve", None)

    stored = decisions.get(decision_id("cand-1", "off-1"))
    assert stored.status == "approved"
    conn.close()


def test_gateway_decider_end_to_end_via_process_interaction():
    conn = connect(":memory:")
    decisions = DecisionStore(conn)
    decisions.save(create_decision(
        candidate_id="cand-1", offer_id="off-1", action="postuler",
        score=90, justification="Bon match",
    ))

    decide = build_gateway_decider(conn)
    process_interaction(_click("reject"), decide=decide, allowlist=ALLOWLIST)

    assert decisions.get(RID).status == "rejected"
    conn.close()
