import { useNavigate } from "react-router-dom";
import { useLaunchRun } from "../api/runs";
import { useProfileReady } from "../api/profile";
import { useTargetCandidate } from "../auth/useTargetCandidate";
import { ProfileRequiredNotice } from "./ProfileRequiredNotice";
import { ErrorNotice } from "./States";

/**
 * Lance un run d'analyse pour la recherche active (OPP-143). La bascule de recherche se fait
 * désormais via le sélecteur global (OPP-184) ; ce raccourci agit donc sur `target`. Au succès,
 * on navigue vers le run créé (et la liste est invalidée pour l'afficher en tête). Rien à lancer
 * sans recherche active.
 *
 * Désactivé tant que le profil est vierge (OPP-219) : analyser sans profil n'a pas de sens (rien
 * à scorer). On oriente alors vers l'import CV plutôt que de laisser l'action échouer.
 *
 * Raccourci partagé entre le cockpit (OPP-164) et l'Historique.
 */
export function LaunchRun() {
  const navigate = useNavigate();
  // `target` reste toujours une recherche du périmètre (cf. useTargetCandidate), donc le POST
  // cible une valeur valide.
  const { target } = useTargetCandidate();
  const launch = useLaunchRun();
  const { ready, isPending: profilePending } = useProfileReady(target);

  if (target === "") return null;

  // Profil vierge (résolu, pas en cours de chargement) → on bloque et on oriente vers l'import.
  const blocked = !ready && !profilePending;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
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
          disabled={launch.isPending || blocked}
          className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-on-brand hover:bg-brand-strong disabled:opacity-50"
        >
          {launch.isPending ? "Analyse en cours…" : "Lancer une analyse"}
        </button>
      </div>
      {blocked && <ProfileRequiredNotice />}
      {launch.data?.total === 0 && launch.data.errors.length === 0 && (
        <p className="text-sm text-ink-muted">Aucune nouvelle offre à évaluer.</p>
      )}
      {launch.isError && <ErrorNotice error={launch.error} />}
    </div>
  );
}
