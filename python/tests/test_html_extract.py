"""Tests de l'extraction de texte HTML (OPP-148). Nécessite l'extra « scrape » (bs4)."""

import pytest

from app.html_extract import extract_offer_text

pytest.importorskip("bs4", reason="extra 'scrape' (beautifulsoup4) requis")


def test_extracts_visible_text():
    html = "<html><body><h1>Développeur Python</h1><p>CDI à Paris.</p></body></html>"
    text = extract_offer_text(html)
    assert "Développeur Python" in text
    assert "CDI à Paris." in text


def test_strips_script_style_and_chrome():
    html = """
    <html><head><style>.a{color:red}</style></head>
    <body>
      <nav>Accueil Connexion</nav>
      <script>trackVisit()</script>
      <main><h1>Data Engineer</h1><p>Python, SQL.</p></main>
      <footer>Mentions légales</footer>
    </body></html>
    """
    text = extract_offer_text(html)
    assert "Data Engineer" in text
    assert "Python, SQL." in text
    # Le bruit structurel disparaît.
    assert "trackVisit" not in text
    assert "color:red" not in text
    assert "Mentions légales" not in text
    assert "Connexion" not in text


def test_collapses_blank_lines():
    html = "<body><p>Un</p><p></p><p>   </p><p>Deux</p></body>"
    assert extract_offer_text(html) == "Un\nDeux"


@pytest.mark.parametrize("html", ["", "   ", None])
def test_empty_html_returns_empty(html):
    assert extract_offer_text(html) == ""


def test_html_without_text_returns_empty():
    assert extract_offer_text("<html><body><script>x()</script></body></html>") == ""
