"""Service d'analyse de CV par LLM (V2, OPP-136).

Symétrique de ``offer_analysis_service`` (OPP-036), côté candidat ::

    texte du CV → prompt structuré → LLMClient → réponse JSON → validation → ProfileAnalysis

Le service dépend du **contrat** ``LLMClient`` (OPP-079), jamais d'Ollama en direct : en
test, on injecte un ``MockLLMClient``. Le prompt est **déterministe** (fonction pure du
texte du CV). Le décodage est contraint au schéma (``fmt``), comme l'analyse d'offre
(OPP-133), pour un JSON fiable même avec un petit modèle local.
"""

from __future__ import annotations

from app.llm_client import LLMClient
from app.profile_analysis import PROFILE_ANALYSIS_SCHEMA, ProfileAnalysis

# Consigne déterministe imposant une sortie JSON stricte aux clés attendues. On n'extrait
# que des **faits** du CV (les préférences — contrat, prétentions… — sont saisies par
# l'utilisateur, pas devinées). ``skills`` atomiques : même exigence que l'analyse d'offre
# (OPP-135), un filet de normalisation existe en aval.
_INSTRUCTIONS = (
    "Tu analyses le CV d'un candidat. Réponds UNIQUEMENT par un objet JSON valide, "
    "sans aucun texte autour, avec exactement ces clés :\n"
    "- name : le nom du candidat ;\n"
    "- location : sa ville ou région principale ;\n"
    "- skills : la liste de ses compétences ;\n"
    "- languages : la liste des langues qu'il parle ;\n"
    "- total_experience_years : le nombre d'années d'expérience professionnelle totale "
    "estimé à partir du CV, ou null si tu ne peux pas l'estimer.\n"
    "Pour skills, donne des compétences ATOMIQUES : une seule technologie ou compétence "
    "par élément (ex. \"Python\", \"SQL\"), jamais de regroupement ni d'énumération dans "
    "un même élément.\n"
    "N'invente aucune préférence (type de contrat, salaire, mobilité) : un CV n'en "
    "contient pas.\n"
    "name et location doivent être renseignés (\"Non précisé\" à défaut).\n\n"
    "CV :\n"
)


def build_profile_prompt(cv_text: str) -> str:
    """Construit le prompt d'analyse de CV (pur et déterministe).

    Lève ``ValueError`` si le texte du CV est vide.
    """
    if not isinstance(cv_text, str) or cv_text.strip() == "":
        raise ValueError("Le texte du CV est requis")
    return _INSTRUCTIONS + cv_text.strip()


def analyze_cv(cv_text: str, client: LLMClient) -> ProfileAnalysis:
    """Analyse un CV textuel en ``ProfileAnalysis`` via le ``client`` LLM.

    Propage ``ValueError`` (CV vide), les erreurs du client (``LLMError`` et sous-classes)
    et ``ProfileAnalysisError`` (réponse non conforme). Le décodage est contraint au schéma
    (``fmt``) pour empêcher le JSON malformé (cf. OPP-133).
    """
    prompt = build_profile_prompt(cv_text)
    response = client.generate(prompt, fmt=PROFILE_ANALYSIS_SCHEMA)
    return ProfileAnalysis.from_json(response.text)
