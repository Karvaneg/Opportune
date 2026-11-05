"""Filtre France des offres d'ATS (OPP-226, RG-12).

Les ATS listent **toutes** les offres d'une entreprise, souvent internationales. Opportune vise
le marché français : on ne garde que les offres localisées en France. Logique pure.

- Lever : champ ``country`` = ``FR``, ou un lieu (``categories.location`` / ``allLocations``) qui
  mentionne la France ;
- Greenhouse : le lieu (``location.name``) ou un bureau (``offices[].name`` / ``.location``) qui
  mentionne la France.

Un lieu « mentionne la France » s'il contient le mot « France » **ou** le nom d'une grande ville
française (``FRENCH_CITIES``) : Greenhouse ne donne souvent que la ville (« Paris »,
« Remote - Lyon »). La comparaison se fait mot à mot, sans casse ni accents, pour que « Nice »
ne corresponde pas à « Venice ».

Une ville française ne suffit pas si elle est **qualifiée par un autre pays ou une région
étrangère** : le morceau qui la suit après une virgule est un pays, un État américain, une
province canadienne (``FOREIGN_PLACES``) ou leur code (``FOREIGN_REGION_CODES`` : « TX »,
« CA »…). « Paris, Texas », « Paris, TX », « Nice, CA » ou « Brest, Belarus » sont donc écartés,
mais « Paris, Berlin, Germany » est gardé : « Germany » qualifie Berlin, pas Paris.

Un lieu qui en liste plusieurs (« Paris or Berlin, Germany », « London; Lyon ») est découpé et
chaque morceau est jugé seul : il suffit qu'un morceau soit en France.

Une offre en télétravail **sans pays identifiable** est écartée : mieux vaut rater une offre
qu'en ajouter une hors marché (« justesse avant richesse »).
"""

from __future__ import annotations

import re

from app.ats_company import GREENHOUSE, LEVER
from app.offer_normalization import strip_accents

# Grandes villes et pôles d'emploi français, écrits sans accents ni tirets (cf. ``_normalize``).
FRENCH_CITIES = (
    "france",
    "paris",
    "la defense",
    "lyon",
    "marseille",
    "toulouse",
    "bordeaux",
    "lille",
    "nantes",
    "nice",
    "sophia antipolis",
    "strasbourg",
    "montpellier",
    "rennes",
    "grenoble",
    "aix en provence",
    "toulon",
    "rouen",
    "nancy",
    "metz",
    "reims",
    "dijon",
    "tours",
    "angers",
    "brest",
    "caen",
    "orleans",
    "clermont ferrand",
    "saint etienne",
    "limoges",
    "annecy",
    "le mans",
    "amiens",
    "pau",
    "biarritz",
    "la rochelle",
    "poitiers",
    "besancon",
    "perpignan",
    "nimes",
    "avignon",
    "mulhouse",
    "le havre",
)

# Pays et régions étrangers qui, accolés à une ville homonyme d'une ville française, montrent
# que le lieu n'est pas en France (« Paris, Texas », « Tours, Belgium »). Même écriture que
# ``FRENCH_CITIES``. Liste volontairement limitée aux noms fréquents dans les lieux d'offres.
FOREIGN_PLACES = (
    # Pays (noms anglais et français).
    "united states", "usa", "etats unis", "united kingdom", "uk", "royaume uni", "england",
    "angleterre", "scotland", "ireland", "irlande", "canada", "mexico", "mexique", "brazil",
    "bresil", "argentina", "argentine", "chile", "chili", "colombia", "colombie", "germany",
    "allemagne", "deutschland", "belgium", "belgique", "netherlands", "pays bas", "luxembourg",
    "switzerland", "suisse", "austria", "autriche", "italy", "italie", "spain", "espagne",
    "portugal", "poland", "pologne", "czech republic", "czechia", "romania", "roumanie",
    "bulgaria", "bulgarie", "hungary", "hongrie", "greece", "grece", "denmark", "danemark",
    "sweden", "suede", "norway", "norvege", "finland", "finlande", "estonia", "estonie",
    "latvia", "lettonie", "lithuania", "lituanie", "ukraine", "belarus", "bielorussie", "russia",
    "russie", "turkey", "turquie", "israel", "egypt", "egypte", "morocco", "maroc", "tunisia",
    "tunisie", "algeria", "algerie", "senegal", "nigeria", "kenya", "south africa",
    "afrique du sud", "india", "inde", "china", "chine", "japan", "japon", "singapore",
    "singapour", "australia", "australie", "new zealand", "nouvelle zelande",
    "united arab emirates", "uae", "emirats arabes unis",
    # États américains et provinces canadiennes qui ont une ville homonyme d'une ville française.
    "texas", "tennessee", "kentucky", "illinois", "missouri", "arkansas", "idaho",
    "ohio", "michigan", "indiana", "new york", "louisiana", "california", "ontario", "quebec",
)


def _word_pattern(names: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(re.escape(name) for name in names) + r")\b")


# Codes à deux lettres des États américains (et DC) et des provinces canadiennes. Ils ne sont
# reconnus que comme morceau **entier** après une virgule (« Paris, TX ») : seuls, « la », « in »
# ou « on » sont aussi des mots courants (« La Défense », « Remote in Paris »).
FOREIGN_REGION_CODES = frozenset(
    "al ak az ar ca co ct de dc fl ga hi id il in ia ks ky la me md ma mi mn ms mo mt ne nv nh "
    "nj nm ny nc nd oh ok or pa ri sc sd tn tx ut vt va wa wv wi wy us "
    "ab bc mb nb nl ns nt nu on pe qc sk yt".split()
)

_FRENCH_PLACE = _word_pattern(FRENCH_CITIES)
_FOREIGN_PLACE = _word_pattern(FOREIGN_PLACES)
# Séparateurs entre plusieurs lieux d'une même offre : « ; », « / », « | », « or », « ou ».
_PLACE_SEPARATOR = re.compile(r"[;/|]|\b(?:or|ou)\b")


def _normalize(text: str) -> str:
    """Minuscules, sans accents, tirets et apostrophes changés en espaces."""
    return re.sub(r"[-'’]", " ", strip_accents(text).casefold())


def _is_foreign_qualifier(segment: str) -> bool:
    """Vrai si le morceau entier est un pays, une région étrangère ou son code (« texas », « tx »)."""
    return segment in FOREIGN_REGION_CODES or _FOREIGN_PLACE.fullmatch(segment) is not None


def _place_in_france(place: str) -> bool:
    """Un lieu seul (déjà normalisé) : « France », ou une ville française non qualifiée par un
    pays ou une région étrangère dans le morceau qui la suit après une virgule."""
    if re.search(r"\bfrance\b", place):
        return True
    segments = [segment.strip() for segment in place.split(",")]
    for index, segment in enumerate(segments):
        if _FRENCH_PLACE.search(segment) is None or _FOREIGN_PLACE.search(segment) is not None:
            continue
        qualifier = segments[index + 1] if index + 1 < len(segments) else ""
        if not _is_foreign_qualifier(qualifier):
            return True
    return False


def _mentions_france(text: object) -> bool:
    if not isinstance(text, str):
        return False
    return any(_place_in_france(place) for place in _PLACE_SEPARATOR.split(_normalize(text)))


def _lever_in_france(posting: dict) -> bool:
    if str(posting.get("country") or "").strip().upper() == "FR":
        return True
    categories = posting.get("categories") or {}
    if not isinstance(categories, dict):
        return False
    places = [categories.get("location")]
    all_locations = categories.get("allLocations")
    if isinstance(all_locations, list):
        places.extend(all_locations)
    return any(_mentions_france(place) for place in places)


def _greenhouse_in_france(job: dict) -> bool:
    location = job.get("location") or {}
    if isinstance(location, dict) and _mentions_france(location.get("name")):
        return True
    offices = job.get("offices") or []
    if not isinstance(offices, list):
        return False
    return any(
        isinstance(office, dict)
        and (_mentions_france(office.get("name")) or _mentions_france(office.get("location")))
        for office in offices
    )


def is_in_france(ats: str, job: dict) -> bool:
    """Vrai si l'offre (JSON brut de l'ATS ``ats``) est localisée en France."""
    if ats == LEVER:
        return _lever_in_france(job)
    if ats == GREENHOUSE:
        return _greenhouse_in_france(job)
    return False
