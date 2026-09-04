import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

/**
 * Accueil MVP : saisie d'un run_id → navigation vers /runs/:runId.
 * Le listing des runs (GET /runs) est hors périmètre (OPP-101).
 */
export function HomePage() {
  const [runId, setRunId] = useState("");
  const navigate = useNavigate();

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = runId.trim();
    if (trimmed) navigate(`/runs/${encodeURIComponent(trimmed)}`);
  }

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Consulter un run</h2>
        <p className="mt-1 text-sm text-slate-500">
          Entrez l'identifiant d'un run pour afficher son détail et ses recommandations.
        </p>
      </div>
      <form onSubmit={onSubmit} className="flex gap-2">
        <input
          value={runId}
          onChange={(e) => setRunId(e.target.value)}
          placeholder="run_id"
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={runId.trim().length === 0}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          Ouvrir
        </button>
      </form>
    </section>
  );
}
