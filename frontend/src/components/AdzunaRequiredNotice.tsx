import { Link } from "react-router-dom";
import { Hint } from "./States";

/**
 * Avertit que la récupération d'offres réelles échouera tant que les clés Adzuna ne sont pas
 * renseignées (OPP-195). Contrairement au profil vierge, la collecte n'est **pas** bloquée : en
 * développement les clés peuvent venir de l'environnement (`.env`), que l'état `configured`
 * (store seul) ne reflète pas. On prévient donc plutôt que d'interdire — sans ce message,
 * l'utilisateur lancerait une passe de plusieurs minutes pour récolter un `source_error` opaque.
 * Le lien mène aux Réglages, où se saisissent les clés.
 */
export function AdzunaRequiredNotice() {
  return (
    <Hint>
      Les clés Adzuna ne sont pas renseignées : sans elles, la récupération d'offres réelles
      échouera. Ajoute-les depuis l'onglet{" "}
      <Link to="/reglages" className="font-medium text-brand hover:underline">
        Réglages
      </Link>
      . Tu peux aussi explorer l'espace Démo ou coller des offres à la main sans aucune clé.
    </Hint>
  );
}
