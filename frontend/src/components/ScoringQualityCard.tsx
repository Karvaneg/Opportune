import { useScoringQuality } from "../api/scoringQuality";
import type { ScoreGroupSummary, ScoringQuality } from "../api/types";

/**
 * Carte « Qualité du score » du cockpit (OPP-234) : les offres que j'ai retenues (approuvées ou
 * postulées) ont-elles un meilleur score que celles que j'ai rejetées ? Le calcul est fait par
 * l'API ; la carte n'affiche une conclusion que si chaque groupe atteint le minimum requis.
 *
 * Carte secondaire : rien n'est affiché tant qu'aucune décision n'est prise (le guide d'accueil
 * suffit), pendant le chargement, ni en cas d'erreur (un bandeau rouge pour une carte
 * indicative alarmerait plus qu'il n'aide).
 */
export function ScoringQualityCard({ candidateId }: { candidateId: string }) {
  const { data } = useScoringQuality(candidateId);
  if (!data || (data.retained.count === 0 && data.rejected.count === 0)) return null;

  return (
    <div className="space-y-3 rounded-lg border border-border bg-surface-raised p-4">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">
        Qualité du score
      </h3>
      <ScoringQualityBody quality={data} />
    </div>
  );
}

function ScoringQualityBody({ quality }: { quality: ScoringQuality }) {
  const { retained, rejected } = quality;

  return (
    <>
      <p className="text-sm text-ink">{verdictText(quality)}</p>
      <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-ink-muted">
              <th className="py-1 font-medium">Offres</th>
              <th className="py-1 font-medium">Score moyen</th>
              <th className="py-1 font-medium">{quality.high_threshold} et plus</th>
              <th className="py-1 font-medium">
                {quality.medium_threshold} à {quality.high_threshold - 1}
              </th>
              <th className="py-1 font-medium">Moins de {quality.medium_threshold}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            <GroupRow label="Retenues" group={retained} />
            <GroupRow label="Rejetées" group={rejected} />
          </tbody>
      </table>
      <p className="text-xs text-ink-muted">
        Retenues : offres approuvées ou postulées. Le score a pu influencer tes décisions, la
        comparaison reste donc indicative.
      </p>
    </>
  );
}

function GroupRow({ label, group }: { label: string; group: ScoreGroupSummary }) {
  return (
    <tr>
      <td className="py-1.5 text-ink">
        {label} ({group.count})
      </td>
      <td className="py-1.5 font-medium text-ink">{formatMean(group.mean)}</td>
      <td className="py-1.5 text-ink-muted">{group.bands.high}</td>
      <td className="py-1.5 text-ink-muted">{group.bands.medium}</td>
      <td className="py-1.5 text-ink-muted">{group.bands.low}</td>
    </tr>
  );
}

/** Phrase de conclusion, ou explication de ce qui manque pour en avoir une. */
export function verdictText(quality: ScoringQuality): string {
  const { retained, rejected, min_per_group: min } = quality;
  if (quality.verdict === "insuffisant") {
    return (
      `Pas encore assez de décisions pour conclure : il faut au moins ${min} offres retenues ` +
      `et ${min} rejetées (tu en as ${retained.count} retenue(s) et ${rejected.count} rejetée(s)).`
    );
  }
  if (quality.verdict === "retenues_mieux_notees") {
    // Écart calculé par l'API sur les moyennes exactes ; sous 0,1 point, l'arrondi donnerait
    // « +0 », d'où une formulation dédiée.
    const gap = quality.gap ?? 0;
    const gapText = gap >= 0.1 ? `+${formatMean(gap)} points` : "écart inférieur à 0,1 point";
    return `Les offres que tu retiens ont en moyenne un meilleur score que celles que tu rejettes (${gapText}) : le score t'aide à trier.`;
  }
  return "Les offres que tu retiens n'ont pas un meilleur score en moyenne que celles que tu rejettes : le score ne t'aide pas encore à trier.";
}

/** Moyenne au dixième, à la française (« 78,5 ») ; tiret si le groupe est vide. */
function formatMean(mean: number | null): string {
  if (mean === null) return "–";
  return mean.toLocaleString("fr-FR", { maximumFractionDigits: 1 });
}
