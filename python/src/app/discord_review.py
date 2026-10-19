"""Revue Discord d'un dossier (V2, OPP-117) — push-to-triage.

Interface de validation humaine de la vision : quand un dossier est prêt (offre +
lettre générée), on le **pousse** dans un salon Discord avec trois boutons
Approuver / Rejeter / Différer. Le clic est routé vers la décision métier existante
(``POST /recommendations/{id}/decision``, OPP-094) — le back de décision est
agnostique de l'interface, ce module n'est qu'un adaptateur.

Découpage (fidèle à l'architecture) :
- **builders purs** : ``build_review_message`` (payload Discord) et l'encodage
  ``custom_id`` ↔ (verbe, recommandation), donc directement testables ;
- **envoi** délégué à un ``DiscordTransport`` injectable (mock en test) ;
- **handler d'interaction** : décode le clic et délègue la décision à un ``decide``
  injecté (idempotent : le back autorise la re-validation).

Ce module ne parle pas au réseau et ne connaît ni le token ni HTTP : il compose des
payloads et route des clics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.cover_letter import CoverLetter
from app.discord_authz import ReviewerAllowlist, extract_discord_user_id
from app.discord_transport import DiscordTransport
from app.offer import Offer
from app.offer_recommendation import ACTION_LABELS

# Verbes de décision (identiques à ceux de l'API, cf. _DECISION_VERBS dans api/app.py).
DECISION_VERBS = ("approve", "reject", "defer")

# Boutons : (verbe, libellé, style Discord). Styles : 3=success, 4=danger, 2=secondary.
_BUTTONS = (
    ("approve", "✅ Approuver", 3),
    ("reject", "❌ Rejeter", 4),
    ("defer", "🕓 Différer", 2),
)

# Préfixe des custom_id de ce module : distingue nos boutons de toute autre interaction.
_CUSTOM_ID_PREFIX = "decide"
# Limite Discord d'un custom_id.
_CUSTOM_ID_MAX = 100

# Marges de sécurité sous les limites d'embed Discord (description ≤ 4096, field ≤ 1024,
# titre ≤ 256) et sous la limite *globale* d'un embed (titre + description + noms +
# valeurs de champs ≤ 6000). La description est budgétée dynamiquement pour respecter ce
# total quand tous les champs sont proches de leur maximum.
_LETTER_MAX = 3800
_FIELD_MAX = 1000
_TITLE_MAX = 256
_EMBED_TOTAL_MAX = 6000

# Valeur de repli : Discord rejette un embed dont un champ (ou la description) est vide.
_PLACEHOLDER = "—"

# Drapeau Discord d'un message éphémère (visible du seul cliqueur).
_EPHEMERAL = 64
# Type de réponse d'interaction « message avec source ».
_RESPONSE_CHANNEL_MESSAGE = 4

# Libellés de confirmation renvoyés au cliqueur.
_CONFIRMATION = {
    "approve": "✅ Dossier approuvé.",
    "reject": "❌ Dossier rejeté.",
    "defer": "🕓 Dossier différé.",
}

# Retour éphémère lorsqu'un cliqueur hors allowlist tente de valider (OPP-124).
_UNAUTHORIZED = "⛔ Tu n'es pas autorisé·e à valider ce dossier."


class InteractionError(Exception):
    """L'interaction reçue n'est pas un clic de décision exploitable."""


def _truncate(text: str, limit: int) -> str:
    """Tronque proprement à ``limit`` caractères (marqueur « … » si coupé)."""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def encode_custom_id(verb: str, recommendation_id: str) -> str:
    """Encode ``(verbe, recommandation)`` dans un ``custom_id`` de bouton.

    Forme : ``decide:<verbe>:<recommendation_id>``. Le ``recommendation_id`` (qui peut
    contenir des ``:``) est conservé verbatim en fin de chaîne, décodé via un
    ``split`` borné. Lève ``ValueError`` si le verbe est inconnu ou si l'id dépasse la
    limite Discord (100 caractères).
    """
    if verb not in DECISION_VERBS:
        raise ValueError(f"verbe inconnu : {verb!r}")
    if not isinstance(recommendation_id, str) or recommendation_id == "":
        raise ValueError("recommendation_id est requis")
    custom_id = f"{_CUSTOM_ID_PREFIX}:{verb}:{recommendation_id}"
    if len(custom_id) > _CUSTOM_ID_MAX:
        raise ValueError(
            f"custom_id trop long ({len(custom_id)} > {_CUSTOM_ID_MAX}) : "
            "identifiant de recommandation trop long pour un bouton Discord"
        )
    return custom_id


def decode_custom_id(custom_id: str) -> tuple[str, str]:
    """Décode un ``custom_id`` en ``(verbe, recommendation_id)``.

    Lève ``InteractionError`` si le préfixe, le verbe ou l'id est absent/invalide.
    """
    if not isinstance(custom_id, str):
        raise InteractionError("custom_id manquant")
    parts = custom_id.split(":", 2)
    if (
        len(parts) != 3
        or parts[0] != _CUSTOM_ID_PREFIX
        or parts[1] not in DECISION_VERBS
        or parts[2] == ""
    ):
        raise InteractionError(f"custom_id non reconnu : {custom_id!r}")
    return parts[1], parts[2]


def _field(name: str, value: str, *, inline: bool) -> dict:
    """Champ d'embed dont la ``value`` est garantie non vide (contrainte Discord : 1..1024)."""
    return {
        "name": name,
        "value": _truncate(value, _FIELD_MAX) or _PLACEHOLDER,
        "inline": inline,
    }


def _decision_buttons(recommendation_id: str) -> dict:
    """Ligne d'action (``type`` 1) portant les trois boutons de décision."""
    return {
        "type": 1,
        "components": [
            {
                "type": 2,
                "style": style,
                "label": label,
                "custom_id": encode_custom_id(verb, recommendation_id),
            }
            for verb, label, style in _BUTTONS
        ],
    }


# Style d'embed par action, pour distinguer d'un coup d'œil « Candidater » de « À étudier »
# dans le salon (OPP-141) : (emoji de titre, couleur d'embed). Le libellé affichable vient
# d'``ACTION_LABELS`` (source unique, cf. offer_recommendation) — pas de recopie ici.
_ACTION_STYLE = {
    "postuler": ("🟢", 0x2ECC71),
    "a_etudier": ("🟡", 0xE67E22),
}
_DEFAULT_ACTION_STYLE = ("⚪", 0x95A5A6)


def build_review_message(
    offer: Offer,
    cover_letter: CoverLetter,
    recommendation_id: str,
    *,
    score: int | None,
    action: str,
    justification: str,
) -> dict:
    """Construit le payload Discord d'un dossier à valider (embed + boutons).

    Pur et déterministe. L'embed résume l'offre (titre, entreprise, score, action
    automatique, justification) et porte la lettre générée ; les trois boutons
    encodent la recommandation. Le titre est préfixé d'un emoji et l'embed coloré selon
    l'action (🟢 candidater / 🟡 à étudier), pour que l'humain repère d'emblée les dossiers
    « à creuser » (OPP-141). Les textes sont tronqués sous les limites Discord — par champ
    *et* sous la limite globale de 6000 caractères —, et aucun champ n'est laissé vide.
    """
    emoji, color = _ACTION_STYLE.get(action, _DEFAULT_ACTION_STYLE)
    title = _truncate(f"{emoji} {offer.title} — {offer.company}", _TITLE_MAX) or _PLACEHOLDER
    fields = [
        # Une formation (OPP-166) n'a pas de score d'adéquation : tiret, jamais « None » ni 0.
        _field("Score", str(score) if score is not None else "—", inline=True),
        _field("Action auto", ACTION_LABELS.get(action, action), inline=True),
        _field("Justification", justification, inline=False),
    ]
    # Budget restant pour la description sous la limite globale de l'embed (6000) :
    # ce qui n'est pas consommé par le titre, les noms de champs et leurs valeurs.
    used = len(title) + sum(len(f["name"]) + len(f["value"]) for f in fields)
    description_limit = min(_LETTER_MAX, _EMBED_TOTAL_MAX - used)
    description = _truncate(cover_letter.body, description_limit) or _PLACEHOLDER
    embed = {"title": title, "description": description, "fields": fields, "color": color}
    return {"embeds": [embed], "components": [_decision_buttons(recommendation_id)]}


@dataclass(frozen=True)
class ReviewSubmission:
    """Résultat d'un push : le message créé et la recommandation qu'il porte."""

    message_id: str
    channel_id: str
    recommendation_id: str


class DiscordReviewer:
    """Pousse un dossier à valider dans un salon Discord (via un transport injecté)."""

    def __init__(self, transport: DiscordTransport, *, channel_id: str) -> None:
        self._transport = transport
        self._channel_id = channel_id

    def submit_for_review(
        self,
        offer: Offer,
        cover_letter: CoverLetter,
        recommendation_id: str,
        *,
        score: int | None,
        action: str,
        justification: str,
    ) -> ReviewSubmission:
        """Construit puis envoie le message de revue ; retourne le mapping message↔reco."""
        message = build_review_message(
            offer,
            cover_letter,
            recommendation_id,
            score=score,
            action=action,
            justification=justification,
        )
        response = self._transport.send_message(self._channel_id, message)
        return ReviewSubmission(
            message_id=response["id"],
            channel_id=self._channel_id,
            recommendation_id=recommendation_id,
        )


# Décideur injecté : (recommendation_id, verbe, commentaire) -> résultat (ignoré ici).
# En production, un appel à POST /recommendations/{id}/decision ; en test, un espion.
DecideFn = Callable[[str, str, "str | None"], object]


def handle_interaction(
    interaction: dict, decide: DecideFn, *, allowlist: ReviewerAllowlist
) -> dict:
    """Route un clic de bouton vers la décision métier, après contrôle d'autorisation.

    ``interaction`` est le payload envoyé par Discord au clic ; ``decide`` applique la
    décision (idempotente côté back) ; ``allowlist`` porte les IDs Discord habilités à
    valider (OPP-124). Le flux : décoder le clic, **vérifier que le cliqueur est autorisé**,
    puis seulement décider. Un cliqueur hors allowlist reçoit un refus éphémère et
    **aucune décision n'est enregistrée** (``decide`` n'est pas appelé). Retourne une
    réponse d'interaction éphémère ; lève ``InteractionError`` si le clic n'est pas une
    décision reconnue.
    """
    data = interaction.get("data") if isinstance(interaction, dict) else None
    custom_id = data.get("custom_id") if isinstance(data, dict) else None
    verb, recommendation_id = decode_custom_id(custom_id)

    if not allowlist.is_allowed(extract_discord_user_id(interaction)):
        return {
            "type": _RESPONSE_CHANNEL_MESSAGE,
            "data": {"content": _UNAUTHORIZED, "flags": _EPHEMERAL},
        }

    decide(recommendation_id, verb, None)
    return {
        "type": _RESPONSE_CHANNEL_MESSAGE,
        "data": {"content": _CONFIRMATION[verb], "flags": _EPHEMERAL},
    }
