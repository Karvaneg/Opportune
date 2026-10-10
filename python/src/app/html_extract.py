"""Extraction du texte pertinent d'une page HTML d'offre (V2, OPP-148).

Transforme le HTML brut (``url_fetch``) en texte exploitable par l'intake (OPP-145) :
retire le bruit structurel (scripts, styles, navigation, pieds de page…) et aplatit le
reste en lignes lisibles. Extraction « readability-lite » via **BeautifulSoup** — confiné
dans l'extra ``scrape`` (``pip install -e ".[scrape]"``) : le cœur métier reste sans
dépendance, et l'import de bs4 est **paresseux** pour qu'un back sans l'extra démarre quand
même (seule cette fonction échoue alors, avec un message clair).
"""

from __future__ import annotations

# Balises retirées avant extraction : ni contenu d'offre, ni texte lisible.
_STRIP_TAGS = (
    "script",
    "style",
    "noscript",
    "template",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    "svg",
)


def extract_offer_text(html: str) -> str:
    """Extrait le texte pertinent d'une page HTML (ou ``""`` si rien d'exploitable).

    Retire le bruit structurel, concatène le texte des éléments restants ligne à ligne,
    et normalise les blancs (pas de lignes vides en rafale). Lève ``RuntimeError`` si
    l'extra ``scrape`` (BeautifulSoup) n'est pas installé — message actionnable.
    """
    try:
        from bs4 import BeautifulSoup
    except ModuleNotFoundError as exc:  # pragma: no cover - dépend de l'environnement
        raise RuntimeError(
            "Extraction HTML indisponible : installez l'extra 'scrape' "
            '(pip install -e ".[scrape]").'
        ) from exc

    if not isinstance(html, str) or html.strip() == "":
        return ""

    soup = BeautifulSoup(html, "html.parser")
    for element in soup(_STRIP_TAGS):
        element.decompose()

    # separator="\n" : chaque bloc sur sa ligne ; strip=True : retire les blancs de bord.
    text = soup.get_text(separator="\n", strip=True)
    # Compacte les lignes vides consécutives laissées par les éléments retirés.
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)
