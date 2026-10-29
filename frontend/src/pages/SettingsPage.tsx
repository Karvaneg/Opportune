import { AdzunaSettings } from "../components/AdzunaSettings";

/**
 * Page « Réglages » (OPP-222) : la configuration locale de l'app, aujourd'hui les clés API de la
 * collecte d'offres (Adzuna). Regroupée à part des pages du périmètre (accueil, profil, offres) :
 * c'est une configuration machine, pas du contenu lié à une recherche.
 */
export function SettingsPage() {
  return (
    <section className="space-y-6">
      <h2 className="text-xl font-semibold text-ink">Réglages</h2>
      <AdzunaSettings />
    </section>
  );
}
