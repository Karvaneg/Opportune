import { Link } from "react-router-dom";

/**
 * Invite à renseigner le profil (import CV) avant une action qui l'exige — collecte d'offres,
 * lancement d'analyse (OPP-219). Affichée sous un bouton désactivé tant que le profil est vierge ;
 * le lien mène à l'onglet Profil, où se fait l'import du CV (OPP-218). Sur la page Offres, une
 * seule invite en tête de page couvre la collecte et l'analyse (OPP-238) : `action` nomme alors
 * ce qu'elle débloque.
 */
export function ProfileRequiredNotice({ action = "cette action" }: { action?: string }) {
  return (
    <p className="text-sm text-ink-muted">
      Ajoute d'abord ton CV depuis l'onglet{" "}
      <Link to="/profil" className="font-medium text-brand hover:underline">
        Profil
      </Link>{" "}
      pour activer {action}.
    </p>
  );
}
