import { Link, useSearchParams } from "react-router-dom";
import { useRunRecommendations } from "../api/runs";
import type { AdvisoryStatus, DecisionStatus } from "../api/types";
import { useBackState } from "../api/useBackState";
import { useClampPage, usePageParam } from "../api/usePageParam";
import { useSearchParamsUpdate } from "../api/useSearchParamsUpdate";
import { Pager } from "./Pager";

import { ErrorNotice, Loading } from "./States";
import { StatusBadge } from "./StatusBadge";

// Options de filtre fermées : seules des valeurs du contrat back transitent (OPP-109).
const ADVISORY_OPTIONS: { value: AdvisoryStatus; label: string }[] = [
  { value: "approved", label: "Pré-approuvé" },
  { value: "pending", label: "En attente" },
  { value: "rejected", label: "Pré-rejeté" },
];
const DECISION_OPTIONS: { value: DecisionStatus; label: string }[] = [
  { value: "pending", label: "À décider" },
  { value: "approved", label: "Approuvé" },
  { value: "rejected", label: "Rejeté" },
  { value: "deferred", label: "Reporté" },
];

/**
 * Consultation paginée des recommandations d'un run, filtrable par statut (OPP-100/109). La
 * page et les filtres sont dans l'adresse (`?page=`, `?advisory=`, `?decision=`, OPP-240) : le
 * retour depuis une fiche ramène à la même liste. Une valeur de filtre inconnue vaut « Toutes ».
 */
export function RunRecommendations({ runId }: { runId: string }) {
  // Retour d'une fiche : ce run avec sa page et ses filtres ; `fromState` garde l'origine du
  // run (page de l'Historique) pour « Changer de run » (OPP-240).
  const backState = useBackState();
  const [searchParams] = useSearchParams();
  const updateParams = useSearchParamsUpdate();
  const [page, setPage] = usePageParam();
  const advisory = pick(searchParams.get("advisory"), ADVISORY_OPTIONS);
  const decision = pick(searchParams.get("decision"), DECISION_OPTIONS);
  const { data, isPending, isError, error, isFetching, isPlaceholderData } = useRunRecommendations(
    runId,
    page,
    { advisoryStatus: advisory, decisionStatus: decision },
  );
  useClampPage(page, setPage, { data, isPlaceholderData, isFetching });

  // Un changement de filtre recadre la pagination sur la page 1.
  const setFilter = (key: "advisory" | "decision", value: string) =>
    updateParams((params) => {
      if (value) params.set(key, value);
      else params.delete(key);
      params.delete("page");
    });

  return (
    <div className="space-y-3">
      {/* Barre de filtres toujours visible (même sur liste vide → on peut réinitialiser). */}
      <div className="flex flex-wrap gap-3 text-sm text-ink-muted">
        <label>
          Pré-évaluation
          <select
            aria-label="Filtre pré-évaluation"
            value={advisory}
            onChange={(e) => setFilter("advisory", e.target.value)}
            className="ml-2 rounded-md border border-border px-2 py-1"
          >
            <option value="">Toutes</option>
            {ADVISORY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Décision
          <select
            aria-label="Filtre décision"
            value={decision}
            onChange={(e) => setFilter("decision", e.target.value)}
            className="ml-2 rounded-md border border-border px-2 py-1"
          >
            <option value="">Toutes</option>
            {DECISION_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {isPending ? (
        <Loading label="Chargement des recommandations…" />
      ) : isError ? (
        <ErrorNotice error={error} />
      ) : data.total === 0 ? (
        <p className="rounded-lg border border-dashed border-border bg-surface-raised p-6 text-center text-sm text-ink-muted">
          Aucune recommandation à afficher.
        </p>
      ) : (
        <>
          {/* Légende : chaque offre porte deux badges de registres distincts (OPP-149). */}
          <p className="text-xs text-ink-muted">
            Pour chaque offre : <span className="text-ink">score au moment du run</span>,
            puis <span className="text-ink">pré-évaluation automatique</span> et{" "}
            <span className="text-ink">décision humaine</span>. Le score à jour (recalculé)
            est visible dans l'onglet Offres et sur le détail de l'offre.
          </p>
          <ul className="space-y-2">
            {data.items.map((item) => (
              <li
                key={item.recommendation_id}
                className="flex items-start justify-between gap-4 rounded-lg border border-border bg-surface-raised p-4"
              >
                <div>
                  <Link
                    to={`/recommendations/${encodeURIComponent(item.recommendation_id)}`}
                    state={backState}
                    className="font-medium text-ink hover:underline"
                  >
                    {item.title || item.offer_id}
                  </Link>
                  <p className="text-sm text-ink-muted">{item.company || "—"}</p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span
                    className="text-sm font-semibold text-ink"
                    title="Score au moment du run (figé). Le score à jour est dans l'onglet Offres."
                  >
                    {item.score}
                  </span>
                  <StatusBadge kind="advisory" value={item.advisory_status} />
                  <StatusBadge kind="decision" value={item.decision_status} />
                </div>
              </li>
            ))}
          </ul>

          <Pager
            page={data.page}
            totalPages={data.total_pages}
            total={data.total}
            onPrev={() => setPage(Math.max(1, page - 1))}
            onNext={() => setPage(page + 1)}
            busy={isFetching}
          />
        </>
      )}
    </div>
  );
}

/** Valeur de filtre lue dans l'adresse : une des options connues, sinon « Toutes » (`""`). */
function pick<T extends string>(raw: string | null, options: { value: T }[]): T | "" {
  return options.find((o) => o.value === raw)?.value ?? "";
}
