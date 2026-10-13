"""Tests du parseur de flux RSS/Atom (OPP-122). Pur, sans réseau."""

import pytest

from app.rss_feed import FeedItem, RssParseError, parse_feed

RSS_2 = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Offres</title>
    <item>
      <title>Développeur Python</title>
      <link>https://example.fr/jobs/1</link>
      <description>&lt;p&gt;Poste &lt;b&gt;CDI&lt;/b&gt;&lt;/p&gt;</description>
    </item>
    <item>
      <title>Data Engineer</title>
      <link>https://example.fr/jobs/2</link>
      <description>Mission data</description>
    </item>
  </channel>
</rss>"""

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Offres</title>
  <entry>
    <title>Dev Python</title>
    <link rel="self" href="https://example.fr/self"/>
    <link rel="alternate" href="https://example.fr/jobs/1"/>
    <summary>Résumé du poste</summary>
  </entry>
</feed>"""

RDF = """<?xml version="1.0"?>
<rdf:RDF xmlns="http://purl.org/rss/1.0/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <item rdf:about="https://example.fr/jobs/9">
    <title>Ingénieur</title>
    <link>https://example.fr/jobs/9</link>
    <description>Desc</description>
  </item>
</rdf:RDF>"""

CONTENT_ENCODED = """<?xml version="1.0"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <item>
      <title>T</title>
      <link>https://example.fr/j</link>
      <description>extrait court</description>
      <content:encoded>contenu riche et complet</content:encoded>
    </item>
  </channel>
</rss>"""


def test_parses_rss_2_items():
    items = parse_feed(RSS_2)
    assert len(items) == 2
    assert items[0] == FeedItem(
        title="Développeur Python",
        link="https://example.fr/jobs/1",
        summary="<p>Poste <b>CDI</b></p>",
    )
    assert items[1].title == "Data Engineer"


def test_parses_atom_and_prefers_alternate_link():
    (item,) = parse_feed(ATOM)
    assert item.title == "Dev Python"
    assert item.link == "https://example.fr/jobs/1"  # alternate, pas self
    assert item.summary == "Résumé du poste"


def test_parses_rdf_rss_1_items():
    (item,) = parse_feed(RDF)
    assert item.title == "Ingénieur"
    assert item.link == "https://example.fr/jobs/9"


def test_content_encoded_wins_over_description():
    (item,) = parse_feed(CONTENT_ENCODED)
    assert item.summary == "contenu riche et complet"


def test_valid_feed_without_items_is_empty():
    assert parse_feed("<rss version='2.0'><channel><title>Vide</title></channel></rss>") == []


def test_item_without_title_and_summary_is_skipped():
    xml = "<rss version='2.0'><channel><item><link>https://x/1</link></item></channel></rss>"
    assert parse_feed(xml) == []


def test_malformed_xml_raises():
    with pytest.raises(RssParseError):
        parse_feed("<rss><channel><item>pas fermé")


def test_empty_string_raises():
    with pytest.raises(RssParseError):
        parse_feed("   ")
