"""Tests de la revue Discord d'un dossier (OPP-117).

Aucun appel réseau : envoi via ``MockDiscordTransport``, décision via un espion.
"""

import pytest

from app.cover_letter import CoverLetter
from app.discord_review import (
    DiscordReviewer,
    InteractionError,
    ReviewSubmission,
    build_review_message,
    decode_custom_id,
    encode_custom_id,
    handle_interaction,
)
from app.discord_authz import ReviewerAllowlist
from app.discord_transport import MockDiscordTransport
from app.offer import Offer

# Une recommandation dont l'id contient un « : » (forme candidate:offre) — vérifie que
# l'encodage/décodage du custom_id le préserve verbatim.
RID = "cand-1:abc123def456"

# Reviewer autorisé + allowlist le contenant, pour les tests de handle_interaction.
REVIEWER_ID = "discord-user-1"
ALLOWLIST = ReviewerAllowlist(frozenset({REVIEWER_ID}))


def _click(custom_id: str, *, user_id: str = REVIEWER_ID) -> dict:
    """Payload d'interaction (contexte salon : identité sous ``member.user``)."""
    return {"data": {"custom_id": custom_id}, "member": {"user": {"id": user_id}}}


def _offer() -> Offer:
    return Offer(
        id="abc123def456",
        title="Développeuse Python",
        company="Acme",
        location="Paris",
        skills=["Python"],
        seniority="Senior",
        contract_type="CDI",
        summary="Backend data.",
        attention_points=[],
        source="collée",
        url="",
        raw_text="...",
    )


def _letter(body: str = "Madame, Monsieur, " + "texte " * 30) -> CoverLetter:
    return CoverLetter(body=body.strip(), model="mock")


# --- custom_id ---------------------------------------------------------------


def test_custom_id_roundtrip_preserves_id_with_colons():
    for verb in ("approve", "reject", "defer"):
        assert decode_custom_id(encode_custom_id(verb, RID)) == (verb, RID)


def test_encode_rejects_unknown_verb():
    with pytest.raises(ValueError):
        encode_custom_id("maybe", RID)


def test_encode_rejects_too_long_id():
    with pytest.raises(ValueError):
        encode_custom_id("approve", "x" * 100)


def test_decode_rejects_foreign_or_malformed_custom_id():
    for bad in ("other:approve:rid", "decide:maybe:rid", "decide:approve:", "n'importe"):
        with pytest.raises(InteractionError):
            decode_custom_id(bad)


# --- build_review_message ----------------------------------------------------


def test_build_message_carries_offer_letter_and_three_buttons():
    message = build_review_message(
        _offer(), _letter(), RID, score=82, action="postuler", justification="Bon match"
    )
    embed = message["embeds"][0]
    assert "Développeuse Python" in embed["title"]
    assert "Madame, Monsieur" in embed["description"]
    assert any(f["value"] == "82" for f in embed["fields"])

    buttons = message["components"][0]["components"]
    assert [b["custom_id"] for b in buttons] == [
        encode_custom_id(v, RID) for v in ("approve", "reject", "defer")
    ]


def test_build_message_distinguishes_action_visually():
    # OPP-141 : « à étudier » doit être reconnaissable (emoji + couleur + libellé) d'un
    # « candidater », pour que l'humain sache sur quoi son jugement est requis.
    postuler = build_review_message(
        _offer(), _letter(), RID, score=82, action="postuler", justification="—"
    )["embeds"][0]
    a_etudier = build_review_message(
        _offer(), _letter(), RID, score=70, action="a_etudier", justification="—"
    )["embeds"][0]

    assert postuler["color"] != a_etudier["color"]
    assert postuler["title"].startswith("🟢") and a_etudier["title"].startswith("🟡")
    assert any(f["value"] == "Candidater" for f in postuler["fields"])
    assert any(f["value"] == "À étudier" for f in a_etudier["fields"])


def test_build_message_truncates_long_letter_under_discord_limit():
    message = build_review_message(
        _offer(), _letter("A" * 5000), RID, score=10, action="ignorer", justification="—"
    )
    description = message["embeds"][0]["description"]
    assert len(description) <= 4096
    assert description.endswith("…")


def test_build_message_replaces_empty_content_with_placeholder():
    # Discord rejette un champ (ou une description) vide : on ne doit jamais en produire.
    message = build_review_message(
        _offer(), _letter(""), RID, score=0, action="", justification="   "
    )
    embed = message["embeds"][0]
    assert embed["description"] != ""
    assert all(field["value"] != "" for field in embed["fields"])


def test_build_message_stays_under_discord_embed_total():
    # Limite globale d'un embed : titre + description + noms + valeurs de champs ≤ 6000.
    message = build_review_message(
        _offer(),
        _letter("A" * 5000),
        RID,
        score=100,
        action="X" * 3000,
        justification="Y" * 3000,
    )
    embed = message["embeds"][0]
    total = (
        len(embed["title"])
        + len(embed["description"])
        + sum(len(f["name"]) + len(f["value"]) for f in embed["fields"])
    )
    assert total <= 6000


# --- DiscordReviewer (push) --------------------------------------------------


def test_submit_for_review_sends_and_maps_message():
    transport = MockDiscordTransport(message_id="msg-7")
    reviewer = DiscordReviewer(transport, channel_id="chan-9")

    submission = reviewer.submit_for_review(
        _offer(), _letter(), RID, score=82, action="postuler", justification="Bon match"
    )

    assert submission == ReviewSubmission(
        message_id="msg-7", channel_id="chan-9", recommendation_id=RID
    )
    # Le message réellement envoyé porte les boutons de décision.
    sent = transport.sent[0]
    assert sent["channel_id"] == "chan-9"
    assert sent["message"]["components"][0]["components"][0]["custom_id"].startswith(
        "decide:approve:"
    )


# --- handle_interaction ------------------------------------------------------


def test_handle_interaction_routes_click_to_decision():
    calls = []

    def decide(rid, verb, comment):
        calls.append((rid, verb, comment))

    interaction = _click(encode_custom_id("approve", RID))
    response = handle_interaction(interaction, decide, allowlist=ALLOWLIST)

    assert calls == [(RID, "approve", None)]
    assert response["type"] == 4  # message avec source
    assert response["data"]["flags"] == 64  # éphémère
    assert "approuvé" in response["data"]["content"]


def test_handle_interaction_rejects_foreign_custom_id():
    def decide(rid, verb, comment):  # ne doit jamais être appelé
        raise AssertionError("decide ne doit pas être appelé")

    with pytest.raises(InteractionError):
        handle_interaction(_click("other:x:y"), decide, allowlist=ALLOWLIST)


def test_handle_interaction_rejects_missing_data():
    with pytest.raises(InteractionError):
        handle_interaction({}, lambda *a: None, allowlist=ALLOWLIST)


def test_handle_interaction_refuses_unauthorized_clicker():
    def decide(rid, verb, comment):  # ne doit jamais être appelé
        raise AssertionError("aucune décision ne doit être enregistrée")

    interaction = _click(encode_custom_id("approve", RID), user_id="intrus")
    response = handle_interaction(interaction, decide, allowlist=ALLOWLIST)

    # Refus éphémère, aucune décision : le back n'est jamais sollicité.
    assert response["type"] == 4
    assert response["data"]["flags"] == 64
    assert "autorisé" in response["data"]["content"]


def test_handle_interaction_refuses_when_identity_absent():
    def decide(rid, verb, comment):
        raise AssertionError("aucune décision ne doit être enregistrée")

    # Payload sans member ni user : identité introuvable → refus (fail-closed).
    interaction = {"data": {"custom_id": encode_custom_id("approve", RID)}}
    response = handle_interaction(interaction, decide, allowlist=ALLOWLIST)

    assert "autorisé" in response["data"]["content"]


def test_handle_interaction_accepts_direct_message_identity():
    calls = []

    def decide(rid, verb, comment):
        calls.append((rid, verb, comment))

    # En message privé, l'identité est au niveau racine ``user`` (pas ``member``).
    interaction = {
        "data": {"custom_id": encode_custom_id("defer", RID)},
        "user": {"id": REVIEWER_ID},
    }
    handle_interaction(interaction, decide, allowlist=ALLOWLIST)

    assert calls == [(RID, "defer", None)]
