/** Contrôles de pagination réutilisables (listing des runs, reco d'un run…). */
export function Pager({
  page,
  totalPages,
  total,
  onPrev,
  onNext,
  busy = false,
}: {
  page: number;
  totalPages: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
  busy?: boolean;
}) {
  return (
    <div className="flex items-center justify-between text-sm text-slate-500">
      <span>
        Page {page} / {Math.max(totalPages, 1)} · {total} au total
      </span>
      <div className="flex gap-2">
        <button
          onClick={onPrev}
          disabled={page <= 1 || busy}
          className="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-40"
        >
          Précédent
        </button>
        <button
          onClick={onNext}
          disabled={page >= totalPages || busy}
          className="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-40"
        >
          Suivant
        </button>
      </div>
    </div>
  );
}
