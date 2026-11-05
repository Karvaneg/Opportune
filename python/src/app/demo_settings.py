"""Réglages de collecte pré-remplis de l'espace démo (OPP-226).

Pour qu'on puisse essayer la collecte « flux RSS » et « entreprises ciblées » dès l'ouverture de
la démo, sans rien saisir, l'espace démo démarre avec quelques sources déjà renseignées. Elles
correspondent au profil vitrine (« Alex Démo », dev fullstack) :

- flux RSS : We Work Remotely (catégorie full-stack) et Remotive, deux flux d'offres tech
  ouverts qui parsent bien (vérifiés le 2026-11-05 : 92 et 12 offres). Il n'existe pas de flux
  RSS d'offres français gratuit (cf. ``docs/collecte-offres.md``) ;
- entreprises ciblées : Swile (Lever) et Mirakl (Greenhouse), deux entreprises françaises qui
  publient des offres en France (vérifiées le 2026-11-05).

Posées une seule fois au démarrage (``ensure_demo_settings_seeded``), y compris pour une démo
installée avant cette fonctionnalité, puis à chaque « Restaurer l'exemple ». Un fichier témoin
dans le dossier des réglages démo retient qu'elles ont été posées : il ne dépend pas de la base
démo, donc une base ``:memory:`` ne fait pas réécrire les réglages à chaque démarrage. « Repartir
de zéro » les vide comme le reste et garde le témoin, pour qu'un redémarrage ne les remette pas. Les entreprises ne sont pas vérifiées auprès de
leur ATS ici (pas d'appel réseau au démarrage) : leur nombre d'offres reste inconnu jusqu'à
la prochaine collecte.
"""

from __future__ import annotations

from pathlib import Path

from app.ats_companies_store import AtsCompaniesStore
from app.ats_company import AtsCompany, parse_career_url
from app.rss_feeds_store import RssFeedsStore

# Fichier témoin « réglages démo déjà posés », dans le dossier des réglages de la démo.
SEEDED_MARKER = ".reglages-demo-poses"

DEMO_RSS_FEEDS = (
    "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
    "https://remotive.com/remote-jobs/feed",
)

DEMO_CAREER_URLS = (
    "https://jobs.lever.co/swile",
    "https://job-boards.greenhouse.io/mirakl",
)


def demo_ats_companies() -> list[AtsCompany]:
    """Entreprises ciblées de la démo, déduites de leurs URLs de page carrière."""
    return [parse_career_url(url) for url in DEMO_CAREER_URLS]


def seed_demo_settings(*, rss_feeds: RssFeedsStore, ats_companies: AtsCompaniesStore) -> None:
    """Remplace les flux RSS et les entreprises ciblées de la démo par ceux de l'exemple."""
    rss_feeds.save(list(DEMO_RSS_FEEDS))
    ats_companies.save(demo_ats_companies())


def mark_demo_settings_seeded(settings_dir: Path) -> None:
    """Pose le témoin : les réglages de la démo ne seront plus pré-remplis au démarrage."""
    settings_dir.mkdir(parents=True, exist_ok=True)
    (settings_dir / SEEDED_MARKER).touch()


def ensure_demo_settings_seeded(
    settings_dir: Path, *, rss_feeds: RssFeedsStore, ats_companies: AtsCompaniesStore
) -> bool:
    """Pré-remplit les réglages de la démo s'ils ne l'ont jamais été ; rend vrai si c'est fait.

    Le témoin n'est posé qu'après l'écriture réussie : si elle échoue (``OSError``), le prochain
    démarrage réessaie.
    """
    if (settings_dir / SEEDED_MARKER).exists():
        return False
    seed_demo_settings(rss_feeds=rss_feeds, ats_companies=ats_companies)
    mark_demo_settings_seeded(settings_dir)
    return True
