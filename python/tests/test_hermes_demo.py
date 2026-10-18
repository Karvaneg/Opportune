"""Tests de la démo exécutable Hermes (OPP-060).

La démo est déterministe et sans réseau : on vérifie qu'elle déroule la boucle complète
et rend un affichage cohérent, sans re-tester la logique déléguée.
"""

from hermes.demo import (
    CANDIDATE_ID,
    render,
    render_validation,
    run,
    run_with_validation,
)


def test_run_deroule_la_boucle_et_classe_par_date():
    # OPP-152 : ordre par date décroissante (dans la démo, la plus récente est aussi la mieux notée).
    results = run()
    ordered = [(r.recommendation.offer.id, r.decision.score) for r in results]
    assert ordered == [
        ("offer-devpy", 100),
        ("offer-fullstack", 78),
        ("offer-javalead", 11),
    ]
    # Chaque résultat porte une décision pending fraîchement créée.
    assert all(r.decision.status == "pending" for r in results)
    assert all(r.decision.candidate_id == CANDIDATE_ID for r in results)


def test_render_liste_chaque_offre_avec_action_et_statut():
    text = render(run())
    assert CANDIDATE_ID in text
    assert "Développeuse Python @ Acme" in text
    assert "100/100" in text
    assert "postuler (pending)" in text


def test_render_gere_le_cas_vide():
    assert render([]) == "Aucune offre évaluable pour ce candidat."


def test_run_with_validation_approuve_la_meilleure_offre():
    results, approved = run_with_validation()
    assert approved.offer_id == results[0].recommendation.offer.id
    assert approved.status == "approved"
    assert approved.comment == "Profil idéal"
    assert len(approved.history) == 2  # pending + approved


def test_render_validation_affiche_statut_et_commentaire():
    _, approved = run_with_validation()
    text = render_validation(approved)
    assert "offer-devpy" in text
    assert "approved" in text
    assert "Profil idéal" in text
