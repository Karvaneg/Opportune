"""Tests de la conversion HTML → texte en bibliothèque standard (OPP-226)."""

import pytest

from app.html_text import html_to_text


def test_blocks_become_lines_and_list_items_get_a_dash():
    fragment = "<h2>Missions</h2><p>Construire   l'API.</p><ul><li>Python</li><li>SQL</li></ul>"

    text = html_to_text(fragment)

    assert text == "Missions\nConstruire l'API.\n- Python\n- SQL"


def test_entities_are_decoded_and_scripts_ignored():
    fragment = "<p>R&amp;D &eacute;quipe</p><script>alert(1)</script><style>p{}</style>"

    text = html_to_text(fragment)

    assert text == "R&D équipe"


def test_br_breaks_line_and_empty_list_items_disappear():
    fragment = "<p>Ligne 1<br>Ligne 2</p><ul><li></li></ul>"

    text = html_to_text(fragment)

    assert text == "Ligne 1\nLigne 2"


@pytest.mark.parametrize("fragment", ["", "   ", None])
def test_empty_input_gives_empty_text(fragment):
    assert html_to_text(fragment) == ""
