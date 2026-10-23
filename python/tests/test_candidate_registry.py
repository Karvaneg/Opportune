"""Registre du périmètre + périmètre d'auth dynamique (OPP-183).

Le périmètre (``owned_candidates``) n'est plus un ``frozenset`` figé au boot : il est stocké en
base (``CandidateRegistry``) et recalculé à chaque requête par ``LocalAuthProvider``.
"""

import pytest

from app.auth import REVIEWER, LocalAuthProvider, User
from app.candidate_registry import CandidateRegistry
from app.db import connect


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


def test_registry_add_et_list_ids(conn):
    registry = CandidateRegistry(conn)
    assert registry.list_ids() == []
    registry.add("cand-1")
    registry.add("cand-2")
    assert registry.list_ids() == ["cand-1", "cand-2"]


def test_registry_add_est_idempotent(conn):
    registry = CandidateRegistry(conn)
    registry.add("cand-1")
    registry.add("cand-1")  # réinsertion
    assert registry.list_ids() == ["cand-1"]


def test_registry_ensure_insere_en_lot_et_ignore_vides_et_doublons(conn):
    registry = CandidateRegistry(conn)
    registry.add("cand-1")
    registry.ensure(["cand-1", "cand-2", "", "cand-3"])
    assert registry.list_ids() == ["cand-1", "cand-2", "cand-3"]


def test_auth_derive_le_perimetre_du_registre_a_chaque_requete(conn):
    # Périmètre dynamique : le provider est rappelé à chaque authenticate() → un candidat ajouté
    # après le boot entre dans le périmètre sans redémarrage (contrairement au frozenset figé).
    registry = CandidateRegistry(conn)
    registry.add("cand-1")
    base = User(id="moi", role=REVIEWER, owned_candidates=frozenset())
    provider = LocalAuthProvider(base, owned_provider=registry.list_ids)

    user = provider.authenticate({})
    assert user.owned_candidates == frozenset({"cand-1"})
    assert user.owns("cand-1") and not user.owns("cand-2")

    registry.add("cand-2")  # ajout à chaud
    assert provider.authenticate({}).owned_candidates == frozenset({"cand-1", "cand-2"})


def test_auth_sans_provider_sert_l_utilisateur_statique(conn):
    # Rétrocompat : sans provider, le périmètre reste celui du User fourni (utilisé par les tests).
    user = User(id="moi", role=REVIEWER, owned_candidates=frozenset({"cand-1"}))
    assert LocalAuthProvider(user).authenticate({}) is user
