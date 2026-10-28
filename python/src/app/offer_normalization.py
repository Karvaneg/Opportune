"""Normalisation déterministe des champs d'une offre (V2, OPP-037).

Fonctions **pures** (aucun LLM, aucune I/O) appliquées à la sortie d'analyse avant
de construire une ``Offer`` : canonicalisation du type de contrat, nettoyage de la
localisation et dédoublonnage des compétences. Un type de contrat inconnu est
conservé tel quel (nettoyé) plutôt qu'écrasé, pour ne pas perdre d'information.
"""

from __future__ import annotations

import re
import unicodedata


def strip_accents(text: str) -> str:
    """Retire les accents/diacritiques (décomposition NFKD puis suppression des marques
    combinantes) — p. ex. « Développé » → « Developpe ». Utilitaire **partagé** : la
    classification de type d'offre (``offer_kind``) s'appuie dessus pour ne pas redéfinir
    un repli d'accents divergent (NFD vs NFKD)."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


# Synonymes (en minuscules) → forme canonique du type de contrat.
_CONTRACT_SYNONYMS = {
    "cdi": "CDI",
    "contrat à durée indéterminée": "CDI",
    "permanent": "CDI",
    "cdd": "CDD",
    "contrat à durée déterminée": "CDD",
    "freelance": "Freelance",
    "indépendant": "Freelance",
    "independant": "Freelance",
    "mission": "Freelance",
    "consultant": "Freelance",
    "stage": "Stage",
    "internship": "Stage",
    "alternance": "Alternance",
    "apprentissage": "Alternance",
    "intérim": "Intérim",
    "interim": "Intérim",
}


# Tokens alphabétiques (accents compris) pour repérer un synonyme à l'intérieur d'un
# libellé composé (« CDI (permanent) », « CDI - temps plein »).
_CONTRACT_WORD_RE = re.compile(r"[a-zà-ÿ]+", re.IGNORECASE)

# Synonymes mono-mot trop génériques pour être cherchés *à l'intérieur* d'un libellé composé :
# « mission »/« consultant » apparaissent dans quantité de libellés non-freelance (« mission
# d'intérêt général », « consultant junior en CDI »). On les garde en lookup direct (exact) mais
# on les exclut du matching par token, sinon ils réécriraient à tort des libellés entiers.
_CONTRACT_WEAK_SYNONYMS = frozenset({"mission", "consultant"})


def normalize_contract(value: str) -> str:
    """Canonicalise un type de contrat ; conserve la valeur nettoyée si inconnu.

    Gère les libellés **composés** que le LLM produit parfois (« CDI (permanent) »,
    « CDI - temps plein ») : à défaut de synonyme direct, on cherche les synonymes connus
    présents dans le libellé (tokens pour les mots simples, sous-chaîne pour les locutions),
    hors synonymes mono-mot ambigus (``_CONTRACT_WEAK_SYNONYMS``) qu'on ne reconnaît qu'en exact.
    Si tous ceux trouvés désignent la **même** forme canonique, on la retient ; en cas de
    conflit (« CDD puis CDI ») ou d'absence, on conserve la valeur nettoyée — on ne perd ni
    n'invente d'information.
    """
    cleaned = " ".join(value.split())
    lowered = cleaned.lower()
    direct = _CONTRACT_SYNONYMS.get(lowered)
    if direct is not None:
        return direct
    tokens = set(_CONTRACT_WORD_RE.findall(lowered))
    found = {
        canonical
        for synonym, canonical in _CONTRACT_SYNONYMS.items()
        if synonym not in _CONTRACT_WEAK_SYNONYMS
        and ((synonym in tokens) or (" " in synonym and synonym in lowered))
    }
    if len(found) == 1:
        return next(iter(found))
    return cleaned


def normalize_location(value: str) -> str:
    """Nettoie une localisation (espaces superflus réduits)."""
    return " ".join(value.split())


# Séparateurs d'énumération « forts » à l'intérieur d'une compétence composée :
# virgule, point-virgule, puce, barre verticale, parenthèses, retour ligne. On
# éclate toujours dessus (« Back-end (PostgreSQL, Express) » → 3 compétences).
_STRONG_SEPARATORS = re.compile(r"[,;·|()\n]+")

# Termes atomiques courants contenant « / » : ne PAS les éclater (faux positifs).
_SLASH_ATOMIC = {"ci/cd", "tcp/ip", "i/o", "a/b", "and/or"}


def _atomize(skill: str) -> list[str]:
    """Éclate une compétence composée en compétences atomiques.

    Filet déterministe derrière la consigne du prompt (cf. ``offer_analysis_service``) :
    même si le LLM émet un bloc composé, on le sépare pour préserver le match exact de
    ``compare_skills``. Le « / » n'est éclaté (« HTML/CSS/JS ») que hors des acronymes
    atomiques connus (« CI/CD », « TCP/IP »).
    """
    parts: list[str] = []
    for chunk in _STRONG_SEPARATORS.split(skill):
        chunk = chunk.strip()
        if not chunk:
            continue
        if chunk.lower() in _SLASH_ATOMIC or "/" not in chunk:
            parts.append(chunk)
        else:
            parts.extend(piece for piece in chunk.split("/") if piece.strip())
    return parts


def normalize_skills(skills: list[str]) -> list[str]:
    """Éclate, nettoie et dédoublonne des compétences (casse-insensible, ordre conservé)."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in skills:
        for skill in _atomize(raw):
            cleaned = " ".join(skill.split())
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(cleaned)
    return result


# --- Filtrage du bruit d'extraction de skills (OPP-142) ----------------------
# Le petit modèle local extrait parfois comme « skills » des éléments qui n'en
# sont pas. La consigne du prompt (cf. ``offer_analysis_service``) réduit ce bruit
# sans le garantir : ce filet déterministe, volontairement CONSERVATEUR, ne vise
# que les catégories non ambiguës listées au ticket, pour ne pas perdre de vraies
# compétences de niche. Symétrique d'OPP-135 (atomisation), mais côté filtrage.

# Normes/labels et organismes/partenaires qui ne sont pas des compétences. Le
# match porte sur la compétence ENTIÈRE (casse-insensible) : « Microsoft » seul
# est écarté, mais « Microsoft Azure » (techno concrète) survit.
_NON_SKILL_TERMS = frozenset(
    {
        # normes / labels
        "iso",
        "pef",
        "wcag",
        "rgaa",
        "affichage environnemental",
        # organismes / partenaires
        "unesco",
        "ademe",
        "greentech",
        "microsoft",
        # remplissage d'énumération (le petit LLM clôt souvent une liste par « etc. »)
        "etc",
        "etc.",
        "...",
        "…",
    }
)

# Tâches/formulations métier : une compétence qui COMMENCE par une nominalisation
# d'action suivie d'un connecteur « de/des/du/d' » décrit une mission, pas une
# techno (« Optimisation de calculs », « Gestion des droits utilisateurs »,
# « Parsing de documents », « Traitement de données hétérogènes »). Volontairement
# restreint aux verbes d'action sans ambiguïté : on écarte les nominalisations
# trop génériques (« analyse », « suivi », « pilotage »…) qui attrapent de vraies
# compétences (« Analyse de données », « Analyse de risques »).
_TASK_PREFIXES = (
    "optimisation",
    "gestion",
    "conception",
    "parsing",
    "traitement",
    "développement",
    "création",
    "rédaction",
    "maintenance",
    "déploiement",
    "amélioration",
    "réalisation",
    "élaboration",
    "mise en place",
)
# NB : « de la »/« de l' » sont déjà couverts par « es? » (match « de » + limite de
# mot sur l'espace suivant) — inutile de les lister à part.
_TASK_RE = re.compile(
    r"^(?:" + "|".join(re.escape(p) for p in _TASK_PREFIXES) + r")\s+d(?:es?|u|')\b",
    re.IGNORECASE,
)

# Compléments « métier » qui dénotent une compétence reconnue malgré un préfixe
# d'action : « Gestion de projet », « Conception de systèmes », « Développement de
# logiciels » sont des compétences, pas des missions — contrairement à « … de
# calculs / de documents / de données hétérogènes », qui restent du bruit.
_SKILL_COMPLEMENTS = frozenset(
    {
        "projet",
        "projets",
        "produit",
        "produits",
        "système",
        "systèmes",
        "logiciel",
        "logiciels",
    }
)


def _is_non_skill(skill: str) -> bool:
    """Vrai si ``skill`` est du bruit (norme/organisme connu, nombre nu ou tâche formulée)."""
    if skill.lower() in _NON_SKILL_TERMS:
        return True
    # Un « skill » dépourvu de toute lettre n'est qu'un nombre ou un numéro de version
    # orphelin (« 3 », « 8.1 », « 2024 ») que le modèle a détaché d'une techno (« Symfony 3 »)
    # ou d'une durée d'expérience. Une vraie techno porte toujours une lettre (« C++ », « C# »,
    # « .NET », « 3D »), donc on ne risque pas de perdre « Symfony 6.4 » (le complément versionné
    # reste accolé à la techno) — OPP-213.
    if not any(ch.isalpha() for ch in skill):
        return True
    match = _TASK_RE.match(skill)
    if match is None:
        return False
    # Un complément métier reconnu (« … de projet/système/logiciel ») désigne une
    # vraie compétence, pas une mission : dans ce cas on ne filtre pas.
    rest = skill[match.end() :].split()
    return not (rest and rest[0].lower() in _SKILL_COMPLEMENTS)


def drop_non_skills(skills: list[str]) -> list[str]:
    """Retire le bruit d'extraction (normes, organismes, tâches) — OPP-142.

    Filet déterministe conservateur : ne supprime que les catégories évidentes,
    pour que le dénominateur de ``compare_skills`` reflète la vraie adéquation
    technique. Ordre et casse des compétences conservées sont préservés.
    """
    return [skill for skill in skills if not _is_non_skill(skill)]


# --- Ancrage des skills au texte réel de l'offre (OPP-213) -------------------
# Garde-fou anti-INVENTION, distinct de ``drop_non_skills`` (anti-bruit) : le petit
# modèle local « complète » volontiers la stack avec des technos plausibles mais
# absentes de l'annonce (jusqu'à ~75 % des skills sur un extrait Adzuna tronqué). On
# ne conserve que les compétences réellement présentes dans le texte analysé.

# Caractères porteurs de sens dans un nom de techno, conservés par le repli : « + »
# (C++), « # » (C#). Tout le reste — y compris « . », « / », « - » — devient un
# séparateur : « Node.js » et « React.js » s'alignent ainsi sur « node js » / « react js »,
# quelle que soit la ponctuation qui les entoure dans l'annonce.
_SKILL_FOLD_KEEP = frozenset("+#")


def _fold(text: str) -> str:
    """Replie un texte pour comparaison tolérante : sans accents, en minuscules, toute
    ponctuation (hors « + # ») réduite à une espace, suites d'espaces compactées."""
    stripped = strip_accents(text)
    kept = "".join(
        ch if (ch.isalnum() or ch in _SKILL_FOLD_KEEP) else " " for ch in stripped.lower()
    )
    return " ".join(kept.split())


def drop_unanchored_skills(skills: list[str], offer_text: str) -> list[str]:
    """Ne conserve que les compétences **réellement présentes** dans ``offer_text`` — OPP-213.

    Garde-fou déterministe contre l'invention du LLM : on préfère une liste **vide mais juste**
    à une liste riche mais supposée (arbitrage produit — mieux vaut aller lire l'offre que se
    fier à une stack inventée). Volontairement **strict** : l'ancrage exige une correspondance
    sur une **frontière de mot** du texte replié (``_fold``), de sorte qu'un token court
    (« go », « r ») ne matche pas l'intérieur d'un autre mot. On assume de perdre une vraie
    compétence reformulée différemment dans l'annonce plutôt que d'en garder une fabriquée.

    Ordre et casse d'origine des compétences conservées sont préservés. À appliquer **après**
    ``normalize_skills`` (atomisation) pour que chaque compétence testée soit déjà unitaire.
    """
    haystack = f" {_fold(offer_text)} "
    anchored: list[str] = []
    for skill in skills:
        needle = _fold(skill)
        if needle and f" {needle} " in haystack:
            anchored.append(skill)
    return anchored
