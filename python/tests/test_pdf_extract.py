"""Tests de l'extraction de texte PDF (OPP-137).

Aucune dépendance pypdf ni fichier réel : le lecteur de pages est injecté.
"""

import pytest

from hermes.pdf_extract import PdfExtractionError, extract_text_from_pdf


def test_joins_pages_and_strips():
    pages = ["  Marie Le Carvennec\n", "Expérience : 6 ans\n", "  "]
    text = extract_text_from_pdf("cv.pdf", read_pages=lambda _: pages)
    assert text == "Marie Le Carvennec\nExpérience : 6 ans"  # pages vides ignorées, strip


def test_passes_path_to_reader():
    seen = {}

    def reader(path):
        seen["path"] = path
        return ["texte"]

    extract_text_from_pdf("/tmp/mon_cv.pdf", read_pages=reader)
    assert seen["path"] == "/tmp/mon_cv.pdf"


def test_empty_pages_raise_extraction_error():
    with pytest.raises(PdfExtractionError):
        extract_text_from_pdf("cv.pdf", read_pages=lambda _: ["", "   ", "\n"])


def test_no_pages_raise_extraction_error():
    with pytest.raises(PdfExtractionError):
        extract_text_from_pdf("cv.pdf", read_pages=lambda _: [])


def test_empty_path_raises_value_error():
    with pytest.raises(ValueError):
        extract_text_from_pdf("   ", read_pages=lambda _: ["x"])
