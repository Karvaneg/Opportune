import { Link } from "react-router-dom";
import { attentionClass, useSettingsAttention } from "../lib/settingsAttention";
import { Hint } from "./States";

/**
 * Explique pourquoi la récupération Adzuna est désactivée : les clés Adzuna de cet espace ne sont
 * pas renseignées (OPP-195). Depuis OPP-227, l'API n'utilise que les clés saisies dans les
 * Réglages (plus de repli sur le `.env`) : `configured` dit donc vrai et le bouton est bloqué.
 * Le lien mène aux Réglages, où se saisissent les clés. L'encadré clignote quand on survole le
 * bouton désactivé (cf. `requestSettingsAttention`), pour montrer d'où vient le blocage.
 */
export function AdzunaRequiredNotice() {
  const attention = useSettingsAttention();
  return (
    // La clé change à chaque demande : l'encadré est remonté et l'animation rejouée.
    <Hint key={attention} className={attentionClass(attention)}>
      Les clés Adzuna ne sont pas renseignées dans cet espace : la récupération Adzuna est
      désactivée tant qu'elles manquent. Ajoute-les depuis l'onglet{" "}
      <Link to="/reglages" className="font-medium text-brand hover:underline">
        Réglages
      </Link>
      . Tu peux aussi collecter tes flux RSS ou tes entreprises ciblées, ou coller des offres à
      la main, sans aucune clé.
    </Hint>
  );
}
