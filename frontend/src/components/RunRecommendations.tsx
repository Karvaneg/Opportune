import { useState } from "react";
import { Link } from "react-router-dom";
import { useRunRecommendations } from "../api/runs";
import type { AdvisoryStatus, DecisionStatus } from "../api/types";
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

/** Consultation paginée des recommandations d'un run, filtrable par statut (OPP-100/109). */
export function RunRecommendations({ runId }: { runId: string }) {
  const [page, setPage] = useState(1);
  const [advisory, setAdvisory] = useState<AdvisoryStatus | "">("");
  const [decision, setDecision] = useState<DecisionStatus | "">("");
  const { data, isPending, isError, error, isFetching } = useRunRecommendations(runId, page, {
    advisoryStatus: advisory,
    decisionStatus: decision,
  });

  return (
    <div className="space-y-3">
      {/* Barre de filtres toujours visible (même sur liste vide → on peut réinitialiser). */}
      <div className="flex flex-wrap gap-3 text-sm text-slate-600">
        <label>
          Pré-évaluation
          <select
            aria-label="Filtre pré-évaluation"
            value={advisory}
            onChange={(e) => {
              setAdvisory(e.target.value as AdvisoryStatus | "");
              setPage(1); // un changement de filtre recadre la pagination sur la page 1
            }}
            className="ml-2 rounded-md border border-slate-300 px-2 py-1"
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
            onChange={(e) => {
              setDecision(e.target.value as DecisionStatus | "");
              setPage(1);
            }}
            className="ml-2 rounded-md border border-slate-300 px-2 py-1"
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
        <p className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">
          Aucune recommandation à afficher.
        </p>
      ) : (
        <>
          <ul className="space-y-2">
            {data.items.map((item) => (
              <li
                key={item.recommendation_id}
                className="flex items-start justify-between gap-4 rounded-lg border border-slate-200 bg-white p-4"
              >
                <div>
                  <Link
                    to={`/recommendations/${encodeURIComponent(item.recommendation_id)}`}
                    state={{ from: `/runs/${runId}` }}
                    className="font-medium text-slate-900 hover:underline"
                  >
                    {item.title || item.offer_id}
                  </Link>
                  <p className="text-sm text-slate-500">{item.company || "—"}</p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span className="text-sm font-semibold text-slate-700">{item.score}</span>
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
            onPrev={() => setPage((p) => Math.max(1, p - 1))}
            onNext={() => setPage((p) => p + 1)}
            busy={isFetching}
          />
        </>
      )}
    </div>
  );
}
