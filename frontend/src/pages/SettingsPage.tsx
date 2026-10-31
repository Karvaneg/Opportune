import { AdzunaSettings } from "../components/AdzunaSettings";
import { RssSettings } from "../components/RssSettings";

/**
 * Page « Réglages » : la configuration locale de l'app — les clés API de la collecte Adzuna
 * (OPP-222) et les URLs des flux RSS à suivre (OPP-195). Regroupée à part des pages du périmètre
 * (accueil, profil, offres) : c'est une configuration machine, pas du contenu lié à une recherche.
 */
export function SettingsPage() {
  return (
    <section className="space-y-6">
      <h2 className="text-xl font-semibold text-ink">Réglages</h2>
      <AdzunaSettings />
      <RssSettings />
    </section>
  );
}
