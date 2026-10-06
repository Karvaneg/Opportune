import { useState } from "react";
import { useOffers } from "../api/offers";
import { useAuth } from "../auth/AuthContext";
import type { CatalogOffer, RecommendationAction } from "../api/types";
import { Pager } from "../components/Pager";
import { ErrorNotice, Loading } from "../components/States";

/**
 * Catalogue des offres (GET /offers, OPP-146) : toutes les offres du pool, plus récentes
 * d'abord (tri serveur OPP-152), paginées. Un sélecteur de candidat annote chaque offre de
 * son **score de match** pour ce candidat (owner-gated côté API). Complète les runs : ici on
 * voit tout le stock, pas seulement les offres évaluées par un run.
 */
export function OffersPage() {
  const { identity } = useAuth();
  const candidates = identity?.owned_candidate_ids ?? [];
  // Candidat ciblé pour le score. Défaut : le 1er du périmètre → on voit un score d'emblée.
  const [candidate, setCandidate] = useState(candidates[0] ?? "");
  const [page, setPage] = useState(1);
  const target = candidates.includes(candidate) ? candidate : candidates[0] ?? "";
  const { data, isPending, isError, error, isFetching } = useOffers(page, target);

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-xl font-semibold text-slate-900">Offres</h2>
        {candidates.length > 1 && (
          <label className="flex items-center gap-2 text-sm text-slate-500">
            Score pour
            <select
              aria-label="Candidat pour le score de match"
              value={target}
              onChange={(e) => {
                setCandidate(e.target.value);
                setPage(1);
              }}
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            >
              {candidates.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {isPending && <Loading label="Chargement des offres…" />}
      {isError && <ErrorNotice error={error} />}

      {!isError &&
        data &&
        (data.total === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">
            Aucune offre dans le catalogue. Ajoute-en une depuis la page Runs.
          </p>
        ) : (
          <div className="space-y-3">
            <ul className="space-y-2">
              {data.items.map((offer) => (
                <OfferRow key={offer.id} offer={offer} />
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

function OfferRow({ offer }: { offer: CatalogOffer }) {
  return (
    <li className="flex items-center justify-between gap-4 rounded-lg border border-slate-200 bg-white p-4 hover:border-slate-400">
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-slate-900">
          {offer.url ? (
            <a
              href={offer.url}
              target="_blank"
              rel="noreferrer"
              className="hover:underline"
            >
              {offer.title}
            </a>
          ) : (
            offer.title
          )}
        </p>
        <p className="truncate text-sm text-slate-500">
          {offer.company} · {offer.location} · {offer.contract_type} ·{" "}
          {formatDate(offer.created_at)}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-3 text-sm">
        <span className="text-slate-400">{offer.source}</span>
        <ScoreBadge score={offer.score} action={offer.action} />
      </div>
    </li>
  );
}

// Couleur du badge par bande de reco (seuils décidés côté serveur, cf. `RecommendationAction`).
const SCORE_TONES: Record<RecommendationAction, string> = {
  postuler: "bg-emerald-100 text-emerald-800",
  a_etudier: "bg-amber-100 text-amber-800",
  ignorer: "bg-slate-100 text-slate-600",
};

/** Badge de score de match. `null` (non ciblé / non évaluable) → tiret neutre. */
function ScoreBadge({ score, action }: { score: number | null; action: RecommendationAction | null }) {
  if (score === null || action === null) {
    return <span className="text-slate-400" title="Non évalué">—</span>;
  }
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${SCORE_TONES[action]}`}>
      {score}/100
    </span>
  );
}

/** Formatage tolérant : valeur brute si la date n'est pas parsable. */
function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("fr-FR");
}
