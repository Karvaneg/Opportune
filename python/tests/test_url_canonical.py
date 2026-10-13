"""Tests de la canonicalisation d'URL pour le dédoublonnage (OPP-119)."""

from app.url_canonical import canonicalize_url


def test_empty_url_returns_empty():
    assert canonicalize_url("") == ""
    assert canonicalize_url("   ") == ""


def test_lowercases_scheme_and_host_only():
    # Le chemin reste sensible à la casse (identité de ressource) ; schéma et hôte non.
    assert canonicalize_url("HTTPS://Www.Example.COM/Jobs/42") == (
        "https://www.example.com/Jobs/42"
    )


def test_strips_fragment():
    assert canonicalize_url("https://x.com/job/42#apply") == "https://x.com/job/42"


def test_strips_trailing_slash_but_keeps_root():
    assert canonicalize_url("https://x.com/job/42/") == "https://x.com/job/42"
    assert canonicalize_url("https://x.com/") == "https://x.com"


def test_removes_default_port_keeps_custom():
    assert canonicalize_url("http://x.com:80/j") == "http://x.com/j"
    assert canonicalize_url("https://x.com:443/j") == "https://x.com/j"
    assert canonicalize_url("https://x.com:8443/j") == "https://x.com:8443/j"


def test_drops_tracking_params_keeps_meaningful_ones():
    # utm_* et autres paramètres analytiques retirés ; l'identifiant d'offre conservé.
    assert canonicalize_url(
        "https://x.com/job?id=42&utm_source=li&utm_medium=social&gclid=abc"
    ) == "https://x.com/job?id=42"


def test_sorts_remaining_params_for_order_independence():
    assert canonicalize_url("https://x.com/j?b=2&a=1") == canonicalize_url(
        "https://x.com/j?a=1&b=2"
    )


def test_same_offer_two_tracking_links_canonicalize_equal():
    # Le cœur d'OPP-119 : deux liens vers la MÊME offre ne différant que par le tracking
    # et un slash final produisent la même clé.
    a = canonicalize_url("https://x.com/job/42?utm_campaign=spring")
    b = canonicalize_url("https://x.com/job/42/#top")
    assert a == b


def test_non_absolute_url_falls_back_to_lowercase():
    # Pas d'hôte exploitable : repli déterministe, sans lever.
    assert canonicalize_url("Pas Une URL") == "pas une url"


def test_invalid_port_falls_back_without_raising():
    # ``urlsplit(...).port`` lève ValueError sur un port hors plage / non numérique :
    # la canonicalisation doit retomber sur le repli minuscule, jamais lever.
    assert canonicalize_url("https://x.com:99999/Job") == "https://x.com:99999/job"
    assert canonicalize_url("http://x.com:abc/j") == "http://x.com:abc/j"
