import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useLaunchRun, useRuns } from "../api/runs";
import { useAuth } from "../auth/AuthContext";
import type { RunSummary } from "../api/types";
import { Pager } from "../components/Pager";
import { ErrorNotice, Loading } from "../components/States";

/** Accueil : liste paginée des runs du périmètre (GET /runs), + accès direct par ID. */
export function RunsListPage() {
  const [page, setPage] = useState(1);
  const { data, isPending, isError, error, isFetching } = useRuns(page);

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-xl font-semibold text-slate-900">Runs</h2>
        <DirectAccess />
      </div>

      <LaunchRun />

      {isPending && <Loading label="Chargement des runs…" />}
      {isError && <ErrorNotice error={error} />}

      {!isError &&
        data &&
        (data.total === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">
            Aucun run dans votre périmètre.
          </p>
        ) : (
          <div className="space-y-3">
            <ul className="space-y-2">
              {data.items.map((run) => (
                <RunRow key={run.run_id} run={run} />
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
          </div>
        ))}
    </section>
  );
}

function RunRow({ run }: { run: RunSummary }) {
  return (
    <li>
      <Link
        to={`/runs/${encodeURIComponent(run.run_id)}`}
        className="flex items-center justify-between gap-4 rounded-lg border border-slate-200 bg-white p-4 hover:border-slate-400"
      >
        <div>
          <p className="font-mono text-sm text-slate-900">{run.run_id}</p>
          <p className="text-sm text-slate-500">
            {run.candidate_id} · {formatDate(run.executed_at)}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-3 text-sm text-slate-600">
          <span>{run.evaluation_count} offre(s)</span>
          {run.error_count > 0 && (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
              {run.error_count} erreur(s)
            </span>
          )}
        </div>
      </Link>
    </li>
  );
}

/**
 * Lance un run d'analyse pour un candidat du périmètre (OPP-143). Un seul candidat →
 * bouton direct ; plusieurs → sélecteur. Au succès, on navigue vers le run créé (et la
 * liste est invalidée pour l'afficher en tête). Rien à lancer si le périmètre est vide.
 */
function LaunchRun() {
  const { identity } = useAuth();
  const navigate = useNavigate();
  const candidates = identity?.owned_candidate_ids ?? [];
  const [candidate, setCandidate] = useState(candidates[0] ?? "");
  const launch = useLaunchRun();

  if (candidates.length === 0) return null;
  // `candidate` est un state figé au montage : si le périmètre change ensuite (identity
  // re-fetchée), la sélection peut sortir de la liste. On retombe alors sur le 1er candidat
  // pour que la valeur du <select> corresponde toujours à une <option> et que le POST cible
  // un candidat réellement du périmètre.
  const target = candidates.includes(candidate) ? candidate : candidates[0];

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
              onSuccess: (data) => navigate(`/runs/${encodeURIComponent(data.run_id)}`),
            })
          }
          disabled={launch.isPending}
          className="rounded-md bg-slate-800 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-50"
        >
          {launch.isPending ? "Analyse en cours…" : "Lancer une analyse"}
        </button>
      </div>
      {launch.isError && <ErrorNotice error={launch.error} />}
    </div>
  );
}

/** Accès direct à un run par saisie d'ID (secours quand on connaît déjà le run_id). */
function DirectAccess() {
  const [runId, setRunId] = useState("");
  const navigate = useNavigate();

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = runId.trim();
    if (trimmed) navigate(`/runs/${encodeURIComponent(trimmed)}`);
  }

  return (
    <form onSubmit={onSubmit} className="flex gap-2">
      <input
        value={runId}
        onChange={(e) => setRunId(e.target.value)}
        placeholder="run_id…"
        className="w-40 rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
      />
      <button
        type="submit"
        disabled={runId.trim().length === 0}
        className="rounded-md border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-40"
      >
        Ouvrir
      </button>
    </form>
  );
}

/** Formatage tolérant : valeur brute si la date n'est pas parsable. */
function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("fr-FR");
}
