"""Registre du périmètre + périmètre d'auth dynamique (OPP-183).

Le périmètre (``owned_candidates``) n'est plus un ``frozenset`` figé au boot : il est stocké en
base (``CandidateRegistry``) et recalculé à chaque requête par ``LocalAuthProvider``.
"""

import pytest

from app.auth import REVIEWER, LocalAuthProvider, User
from app.candidate_registry import CandidateRegistry, Search
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


def test_registry_create_genere_un_id_et_porte_le_libelle(conn):
    registry = CandidateRegistry(conn)
    search = registry.create("Data Analyst Paris")
    assert search.id and search.label == "Data Analyst Paris"
    # La recherche entre dans le périmètre (ids) et dans la liste nommée.
    assert registry.list_ids() == [search.id]
    assert registry.list() == [Search(id=search.id, label="Data Analyst Paris")]


def test_registry_create_rogne_le_libelle_et_accepte_new_id_injecte(conn):
    registry = CandidateRegistry(conn)
    search = registry.create("  Product Manager  ", new_id=lambda: "search-fixe")
    assert search == Search(id="search-fixe", label="Product Manager")


def test_registry_create_regenere_un_id_en_cas_de_collision(conn):
    registry = CandidateRegistry(conn)
    ids = iter(["search-dup", "search-dup", "search-neuf"])
    registry.create("Première", new_id=lambda: "search-dup")
    search = registry.create("Seconde", new_id=lambda: next(ids))
    assert search.id == "search-neuf"


def test_registry_rename_met_a_jour_le_libelle(conn):
    registry = CandidateRegistry(conn)
    search = registry.create("Ancien nom", new_id=lambda: "search-1")
    assert registry.rename("search-1", "Nouveau nom") is True
    assert registry.list() == [Search(id="search-1", label="Nouveau nom")]


def test_registry_rename_id_inconnu_rend_false(conn):
    registry = CandidateRegistry(conn)
    assert registry.rename("search-absent", "peu importe") is False


def test_registry_add_idempotent_preserve_le_libelle(conn):
    # Un re-seed / bootstrap (``add`` sans libellé) ne doit pas écraser un nom donné à la main.
    registry = CandidateRegistry(conn)
    registry.add("cand-1", label="Mon nom")
    registry.add("cand-1")  # réinsertion sans libellé
    assert registry.list() == [Search(id="cand-1", label="Mon nom")]


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


def test_registry_migre_une_base_sans_colonne_label(conn):
    # Base antérieure à OPP-184 : table ``candidates`` sans ``label``. L'init doit ajouter la
    # colonne (défaut '') plutôt que laisser les requêtes échouer, et préserver les lignes.
    conn.execute("CREATE TABLE candidates (id TEXT PRIMARY KEY, created_at TEXT NOT NULL)")
    conn.execute("INSERT INTO candidates (id, created_at) VALUES ('cand-old', '2026-01-01')")
    conn.commit()

    registry = CandidateRegistry(conn)
    assert registry.list() == [Search(id="cand-old", label="")]
    # Et la colonne est bien exploitable après migration.
    assert registry.rename("cand-old", "Récupéré") is True
    assert registry.list() == [Search(id="cand-old", label="Récupéré")]


def test_auth_sans_provider_sert_l_utilisateur_statique(conn):
    # Rétrocompat : sans provider, le périmètre reste celui du User fourni (utilisé par les tests).
    user = User(id="moi", role=REVIEWER, owned_candidates=frozenset({"cand-1"}))
    assert LocalAuthProvider(user).authenticate({}) is user
