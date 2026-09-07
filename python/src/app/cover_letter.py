"""Modèle de lettre de motivation et validation de la génération (V2, OPP-113).

``CoverLetter`` est le résultat métier structuré du Rédacteur : le corps de la lettre
prêt à relire, plus le modèle LLM effectivement sollicité et le corps brut de réponse
(pour la journalisation / le débogage, sans y coupler le métier).

Ce module ne parle **pas** au LLM : il fixe le contrat de données et **valide** la
génération. Fidèle à la philosophie de la stack (cf. ``offer_analysis``), une réponse
vide ou manifestement tronquée est rejetée par ``CoverLetterError`` — jamais complétée
silencieusement.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Longueur minimale plausible d'une lettre exploitable : garde-fou contre une réponse
# vide ou une génération tronquée. Volontairement bas pour ne rejeter que le
# manifestement inutilisable, pas une lettre courte légitime.
MIN_BODY_LENGTH = 100

# Un refus du modèle est souvent plus long que MIN_BODY_LENGTH (« Je ne peux pas rédiger
# cette lettre car… ») : la longueur seule ne le rattrape pas. On repère les préfixes de
# refus les plus courants (début de génération, casse ignorée) pour les rejeter au lieu
# de renvoyer le refus comme une lettre valide.
_REFUSAL_PREFIXES = (
    "je ne peux pas",
    "je ne peux malheureusement pas",
    "je suis désolé",
    "je suis désolée",
    "désolé",
    "désolée",
    "en tant qu",  # « En tant qu'IA/assistant, je ne peux pas… »
    "i cannot",
    "i can't",
    "i'm sorry",
    "as an ai",
)


class CoverLetterError(Exception):
    """La génération ne forme pas une lettre de motivation exploitable."""


@dataclass(frozen=True)
class CoverLetter:
    """Lettre de motivation générée, prête à relire."""

    body: str
    model: str
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_generation(
        cls, text: str, *, model: str, raw: dict | None = None
    ) -> "CoverLetter":
        """Valide un texte généré et construit la lettre.

        Lève ``CoverLetterError`` si le texte est vide, trop court pour être une lettre
        exploitable (``MIN_BODY_LENGTH``) ou s'il s'agit manifestement d'un refus du
        modèle. Le corps est nettoyé de ses espaces de bord.
        """
        if not isinstance(text, str) or text.strip() == "":
            raise CoverLetterError("Lettre vide : génération inexploitable")
        cleaned = text.strip()
        if len(cleaned) < MIN_BODY_LENGTH:
            raise CoverLetterError(
                f"Lettre trop courte (< {MIN_BODY_LENGTH} caractères) : "
                "génération douteuse"
            )
        lowered = cleaned.lower()
        if any(lowered.startswith(prefix) for prefix in _REFUSAL_PREFIXES):
            raise CoverLetterError("Refus du modèle : génération inexploitable")
        return cls(body=cleaned, model=model, raw=raw or {})
