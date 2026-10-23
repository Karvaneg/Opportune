"""Routeur d'espace « Mon espace / Démo » (OPP-182).

Deux ``HermesApi`` assemblées sur deux bases SQLite distinctes ; le routeur choisit la cible
selon l'en-tête ``X-Opportune-Space``. On vérifie l'aiguillage (header → bonne base), le défaut
sûr (absent/inconnu → « mine », jamais la démo par accident) et l'**isolation** (la démo seedée
n'apparaît pas côté « mine »).
"""

import pytest

from api.app import Response
from api.server import assemble_api, build_local_auth
from api.space_router import SPACE_HEADER, SpaceRouter
from app.db import connect
from app.demo_candidate import DEMO_CANDIDATE_ID, reset_demo, seed_demo_candidate
from app.offer_store import OfferStore

MINE_CANDIDATE_ID = "cand-mine"


def _demo_commands(demo_conn):
    """Les commandes d'espace démo, câblées comme dans ``server.main`` (sur la conn démo)."""

    def reset() -> Response:
        reset_demo(demo_conn)
        return Response(200, {"status": "reset"})

    def restore() -> Response:
        reset_demo(demo_conn)
        seed_demo_candidate(demo_conn)
        return Response(200, {"status": "restored"})

    return {"/demo/reset": reset, "/demo/restore": restore}


@pytest.fixture
def router():
    # « Mon espace » : base vide, périmètre = un candidat réel fictif.
    mine_conn = connect(":memory:")
    mine = assemble_api(mine_conn, build_local_auth([MINE_CANDIDATE_ID]))
    # « Démo » : base séparée, seedée (candidat démo + offres), périmètre = candidat démo.
    demo_conn = connect(":memory:")
    seed_demo_candidate(demo_conn)
    demo = assemble_api(demo_conn, build_local_auth([DEMO_CANDIDATE_ID]))
    router = SpaceRouter(mine=mine, demo=demo, demo_commands=_demo_commands(demo_conn))
    # On expose la conn démo pour les tests de commandes (reset/restore).
    router._test_demo_conn = demo_conn  # type: ignore[attr-defined]
    yield router
    mine_conn.close()
    demo_conn.close()


def _me(router, space):
    headers = {SPACE_HEADER: space} if space is not None else {}
    return router.dispatch("GET", "/me", {}, headers)


def test_header_demo_route_vers_l_espace_demo(router):
    response = _me(router, "demo")
    assert response.status == 200
    assert response.body["owned_candidate_ids"] == [DEMO_CANDIDATE_ID]


def test_header_mine_route_vers_mon_espace(router):
    response = _me(router, "mine")
    assert response.status == 200
    assert response.body["owned_candidate_ids"] == [MINE_CANDIDATE_ID]


def test_header_absent_par_defaut_mon_espace(router):
    # Défaut sûr : jamais la démo sans demande explicite.
    response = _me(router, None)
    assert response.body["owned_candidate_ids"] == [MINE_CANDIDATE_ID]


def test_header_inconnu_retombe_sur_mon_espace(router):
    response = _me(router, "n-importe-quoi")
    assert response.body["owned_candidate_ids"] == [MINE_CANDIDATE_ID]


def test_header_insensible_a_la_casse(router):
    response = router.dispatch("GET", "/me", {}, {"x-opportune-space": "DEMO"})
    assert response.body["owned_candidate_ids"] == [DEMO_CANDIDATE_ID]


def test_isolation_les_offres_demo_sont_invisibles_cote_mine(router):
    # La démo a 5 offres seedées ; « Mon espace » (base séparée, vide) n'en voit aucune.
    path = f"/candidates/{DEMO_CANDIDATE_ID}/stats"
    demo_stats = router.dispatch("GET", path, {}, {SPACE_HEADER: "demo"})
    assert demo_stats.status == 200
    assert demo_stats.body["offres_total"] == 5

    # Le candidat démo n'existe pas (et n'est pas possédé) côté « mine » → pas de 200.
    mine_view = router.dispatch("GET", path, {}, {SPACE_HEADER: "mine"})
    assert mine_view.status != 200


def test_demo_reset_vide_la_base_demo(router):
    demo_conn = router._test_demo_conn
    assert OfferStore(demo_conn).count() == 5
    response = router.dispatch("POST", "/demo/reset", {}, {})
    assert response.status == 200
    assert OfferStore(demo_conn).count() == 0


def test_demo_restore_restaure_la_vitrine(router):
    demo_conn = router._test_demo_conn
    router.dispatch("POST", "/demo/reset", {}, {})
    assert OfferStore(demo_conn).count() == 0
    response = router.dispatch("POST", "/demo/restore", {}, {})
    assert response.status == 200
    assert OfferStore(demo_conn).count() == 5


def test_commande_demo_cible_la_demo_meme_avec_header_mine(router):
    # Sécurité : la commande vise toujours la base démo, quel que soit l'en-tête — jamais le réel.
    demo_conn = router._test_demo_conn
    response = router.dispatch("POST", "/demo/reset", {}, {SPACE_HEADER: "mine"})
    assert response.status == 200
    assert OfferStore(demo_conn).count() == 0
