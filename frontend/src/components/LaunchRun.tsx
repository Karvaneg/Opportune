import { useNavigate } from "react-router-dom";
import { useLaunchRun } from "../api/runs";
import { useTargetCandidate } from "../auth/useTargetCandidate";
import { ErrorNotice } from "./States";

/**
 * Lance un run d'analyse pour un candidat du périmètre (OPP-143). Un seul candidat →
 * bouton direct ; plusieurs → sélecteur. Au succès, on navigue vers le run créé (et la
 * liste est invalidée pour l'afficher en tête). Rien à lancer si le périmètre est vide.
 *
 * Raccourci partagé entre le cockpit (OPP-164) et l'Historique.
 */
export function LaunchRun() {
  const navigate = useNavigate();
  // `target` reste toujours un candidat du périmètre même si `identity` est re-fetchée (cf.
  // useTargetCandidate), garantissant que le <select> et le POST ciblent une valeur valide.
  const { candidates, target, setCandidate } = useTargetCandidate();
  const launch = useLaunchRun();

  if (candidates.length === 0) return null;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {candidates.length > 1 && (
          <select
            aria-label="Candidat à analyser"
            value={target}
            onChange={(e) => setCandidate(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
          >
            {candidates.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        )}
        <button
          type="button"
          onClick={() =>
            launch.mutate(target, {
              // Un run n'évalue que les offres nouvelles (OPP-150). Vraiment vide (aucune
              // évaluation ET aucune erreur) → run non persisté côté back, inutile d'y
              // naviguer : on affiche le message ci-dessous. Mais des erreurs par offre
              // vivent dans un run bien persisté → on y navigue pour les montrer.
              onSuccess: (data) => {
                if (data.total > 0 || data.errors.length > 0)
                  navigate(`/runs/${encodeURIComponent(data.run_id)}`);
              },
            })
          }
          disabled={launch.isPending}
          className="rounded-md bg-slate-800 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-50"
        >
          {launch.isPending ? "Analyse en cours…" : "Lancer une analyse"}
        </button>
      </div>
      {launch.data?.total === 0 && launch.data.errors.length === 0 && (
        <p className="text-sm text-slate-500">Aucune nouvelle offre à évaluer.</p>
      )}
      {launch.isError && <ErrorNotice error={launch.error} />}
    </div>
  );
}
