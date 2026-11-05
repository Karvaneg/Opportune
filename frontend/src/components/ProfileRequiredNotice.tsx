import { Link } from "react-router-dom";

/**
 * Invite à renseigner le profil (import CV) avant une action qui l'exige — collecte d'offres,
 * lancement d'analyse (OPP-219). Affichée sous un bouton désactivé tant que le profil est vierge ;
 * le lien mène à l'onglet Profil, où se fait l'import du CV (OPP-218).
 */
export function ProfileRequiredNotice() {
  return (
    <p className="text-sm text-ink-muted">
      Ajoute d'abord ton CV depuis l'onglet{" "}
      <Link to="/profil" className="font-medium text-brand hover:underline">
        Profil
      </Link>{" "}
      pour activer cette action.
    </p>
  );
}
