import { AdzunaSettings } from "../components/AdzunaSettings";
import { AtsSettings } from "../components/AtsSettings";
import { DataTransferSettings } from "../components/DataTransferSettings";
import { FollowUpSettings } from "../components/FollowUpSettings";
import { RssSettings } from "../components/RssSettings";
import { UninstallSettings } from "../components/UninstallSettings";

/**
 * Page « Réglages » : la configuration locale de l'app — les clés API de la collecte Adzuna
 * (OPP-222), les URLs des flux RSS à suivre (OPP-195) et les pages carrière des entreprises
 * ciblées (OPP-226), les délais de relance (OPP-235), la sauvegarde des données de l'espace
 * (OPP-232) et la désinstallation de l'app de bureau (OPP-252). Regroupée à part des pages du
 * périmètre (accueil, profil, offres) : c'est une configuration machine, pas du contenu lié à
 * une recherche.
 */
export function SettingsPage() {
  return (
    <section className="space-y-6">
      <h2 className="text-xl font-semibold text-ink">Réglages</h2>
      <AdzunaSettings />
      <RssSettings />
      <AtsSettings />
      <FollowUpSettings />
      <DataTransferSettings />
      <UninstallSettings />
    </section>
  );
}
