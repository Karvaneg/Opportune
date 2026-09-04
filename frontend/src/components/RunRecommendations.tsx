import { useState } from "react";
import { useRunRecommendations } from "../api/runs";
import { ErrorNotice, Loading } from "./States";
import { StatusBadge } from "./StatusBadge";

/** Consultation paginée des recommandations d'un run (lecture seule en OPP-100). */
export function RunRecommendations({ runId }: { runId: string }) {
  const [page, setPage] = useState(1);
  const { data, isPending, isError, error, isFetching } = useRunRecommendations(runId, page);

  if (isPending) return <Loading label="Chargement des recommandations…" />;
  if (isError) return <ErrorNotice error={error} />;

  if (data.total === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">
        Aucune recommandation pour ce run.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <ul className="space-y-2">
        {data.items.map((item) => (
          <li
            key={item.recommendation_id}
            className="flex items-start justify-between gap-4 rounded-lg border border-slate-200 bg-white p-4"
          >
            <div>
              <p className="font-medium text-slate-900">{item.title || item.offer_id}</p>
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

      <div className="flex items-center justify-between text-sm text-slate-500">
        <span>
          Page {data.page} / {Math.max(data.total_pages, 1)} · {data.total} au total
        </span>
        <div className="flex gap-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={data.page <= 1 || isFetching}
            className="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-40"
          >
            Précédent
          </button>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={data.page >= data.total_pages || isFetching}
            className="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-40"
          >
            Suivant
          </button>
        </div>
      </div>
    </div>
  );
}
