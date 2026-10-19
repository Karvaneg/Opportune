"""Service d'analyse d'offre par LLM (V2, OPP-036).

Première boucle métier de bout en bout de la stack V2 :

    texte brut → prompt structuré → LLMClient → réponse JSON → validation → OfferAnalysis

Le service dépend du **contrat** ``LLMClient`` (OPP-079), jamais d'Ollama en direct :
en test, on injecte un ``MockLLMClient``. Le prompt est **déterministe** (fonction pure
du texte d'offre), donc directement testable.
"""

from __future__ import annotations

from app.llm_client import LLMClient
from app.offer_analysis import OFFER_ANALYSIS_SCHEMA, OfferAnalysis

# Consigne déterministe imposant une sortie JSON stricte aux clés attendues. Séparée du
# texte d'offre pour rester testable et éviter toute interpolation d'accolades.
_INSTRUCTIONS = (
    "Tu analyses une offre d'emploi. Réponds UNIQUEMENT par un objet JSON valide, "
    "sans aucun texte autour, avec exactement ces clés :\n"
    "- title, company, location, seniority, contract_type, summary : des chaînes ;\n"
    "- skills, attention_points : des listes de chaînes.\n"
    "Pour skills, donne des compétences ATOMIQUES : une seule technologie ou "
    "compétence par élément (ex. \"PostgreSQL\", \"Express\", \"React\"), jamais de "
    "regroupement ni d'énumération dans un même élément (n'écris PAS "
    "\"Back-end (PostgreSQL, Express)\" ni \"HTML/CSS/JS\" — éclate-les).\n"
    "Ne mets dans skills QUE des compétences ou technologies CONCRÈTES (langages, "
    "frameworks, outils, bases de données). N'y mets PAS : les normes ou labels "
    "(ISO, WCAG, RGAA…), les organismes ou partenaires (UNESCO, ADEME, Microsoft…), "
    "ni les tâches ou missions (\"Optimisation de calculs\", \"Gestion des droits "
    "utilisateurs\" — ce ne sont pas des compétences).\n"
    "Chaque champ texte doit être renseigné (\"Non précisé\" s'il est absent de "
    "l'offre).\n"
    "Ajoute aussi \"kind\" : \"formation\" si l'annonce propose un programme de "
    "formation, un cursus, une certification ou une POE (préparation à l'emploi) — "
    "sinon \"emploi\" (cas par défaut d'une offre de poste).\n\n"
    "Offre :\n"
)


def build_analysis_prompt(offer_text: str) -> str:
    """Construit le prompt d'analyse (pur et déterministe).

    Lève ``ValueError`` si le texte d'offre est vide.
    """
    if not isinstance(offer_text, str) or offer_text.strip() == "":
        raise ValueError("Le texte de l'offre est requis")
    return _INSTRUCTIONS + offer_text.strip()


def analyze_offer(offer_text: str, client: LLMClient) -> OfferAnalysis:
    """Analyse une offre textuelle en ``OfferAnalysis`` via le ``client`` LLM.

    Propage ``ValueError`` (offre vide), les erreurs du client (``LLMError`` et
    sous-classes) et ``OfferAnalysisError`` (réponse non conforme).
    """
    prompt = build_analysis_prompt(offer_text)
    # ``fmt`` contraint le décodage au schéma d'``OfferAnalysis`` : le petit modèle local ne
    # peut plus émettre de prose ni de JSON malformé autour de l'objet (cause d'échec de
    # l'intake réel). Le prompt guide toujours le *contenu* (défaut « Non précisé »).
    response = client.generate(prompt, fmt=OFFER_ANALYSIS_SCHEMA)
    return OfferAnalysis.from_json(response.text)
