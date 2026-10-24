import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useEvaluateOffer, useOffers } from "../api/offers";
import { FUNNEL_LABELS, isFunnelStage } from "../api/funnel";
import { useTargetCandidate } from "../auth/useTargetCandidate";
import { useIsReviewer } from "../auth/roles";
import type { CatalogOffer, OfferKind, RecommendationAction } from "../api/types";
import { CollectOffers } from "../components/CollectOffers";
import { Pager } from "../components/Pager";
import { ErrorNotice, Loading } from "../components/States";

/**
 * Catalogue des offres (GET /offers, OPP-146) : toutes les offres du pool, plus récentes
 * d'abord (tri serveur OPP-152), paginées. Un sélecteur de candidat annote chaque offre de
 * son **score de match** pour ce candidat (owner-gated côté API). Complète les runs : ici on
 * voit tout le stock, pas seulement les offres évaluées par un run.
 */
export function OffersPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  // Recherche active pour le score : sélection **partagée** avec le reste de l'app (sélecteur
  // global, OPP-184) — elle suit la navigation, p. ex. depuis une carte-compteur du cockpit.
  const { target } = useTargetCandidate();
  // La curation du pool (collecte Adzuna ci-dessous, ajout depuis l'accueil) est réservée au
  // rôle reviewer : le message de catalogue vide n'oriente vers ces actions que si elles sont
  // réellement disponibles (sinon « ci-dessus » pointerait vers un bloc masqué).
  const isReviewer = useIsReviewer();
  const [page, setPage] = useState(1);
  // Filtre par étape d'entonnoir, piloté par l'URL (clic sur une carte du cockpit, OPP-164).
  const rawStage = searchParams.get("stage");
  const stageFilter = isFunnelStage(rawStage) ? rawStage : null;
  // Bascule de recherche (sélecteur global) : on revient en page 1, sinon on resterait sur une
  // page hors bornes pour une recherche au catalogue plus court.
  useEffect(() => setPage(1), [target]);
  // Filtrage **côté serveur** : le pool entier est filtré avant pagination, donc `total` et le
  // Pager concordent avec les compteurs du cockpit même au-delà d'une page.
  const { data, isPending, isError, error, isFetching } = useOffers(
    page,
    target,
    stageFilter ?? "",
  );
  const items = data?.items ?? [];

  const clearFilter = () => {
    setPage(1);
    setSearchParams(
      (prev) => {
        prev.delete("stage");
        return prev;
      },
      { replace: true },
    );
  };

  return (
    <section className="space-y-6">
      <h2 className="text-xl font-semibold text-ink">Offres</h2>

      <CollectOffers />

      {stageFilter && (
        <div className="flex items-center gap-2 text-sm">
          <span className="rounded-full bg-ink/5 px-3 py-1 text-ink">
            Filtré : {FUNNEL_LABELS[stageFilter]}
          </span>
          <button type="button" onClick={clearFilter} className="text-ink-muted hover:underline">
            effacer le filtre
          </button>
        </div>
      )}

      {isPending && <Loading label="Chargement des offres…" />}
      {isError && <ErrorNotice error={error} />}

      {!isError &&
        data &&
        (data.total === 0 ? (
          <p className="rounded-lg border border-dashed border-border bg-surface-raised p-6 text-center text-sm text-ink-muted">
            {stageFilter
              ? `Aucune offre « ${FUNNEL_LABELS[stageFilter]} » pour cette recherche.`
              : isReviewer
                ? "Aucune offre dans le catalogue. Récupère-en de nouvelles ci-dessus, ou ajoute-en une depuis l'accueil."
                : "Aucune offre dans le catalogue pour le moment."}
          </p>
        ) : (
          <div className="space-y-3">
            <ul className="space-y-2">
              {items.map((offer) => (
                <OfferRow key={offer.id} offer={offer} candidateId={target} />
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

/**
 * Ligne de catalogue. Le **titre ouvre la fiche interne** de l'offre pour le candidat ciblé
 * (OPP-160) : on évalue l'offre à la volée (get-or-create, sans run) puis on navigue vers sa
 * recommandation. Plus besoin de passer par un run. Le lien « voir sur le site » reste
 * accessible en **secondaire**. Sans candidat ciblé, le titre n'est plus cliquable (texte
 * brut) ; l'offre externe reste joignable via ce lien secondaire.
 */
function OfferRow({ offer, candidateId }: { offer: CatalogOffer; candidateId: string }) {
  const navigate = useNavigate();
  const evaluate = useEvaluateOffer();

  const openFiche = () =>
    evaluate.mutate(
      { candidateId, offerId: offer.id },
      {
        onSuccess: (reco) =>
          navigate(`/recommendations/${encodeURIComponent(reco.recommendation_id)}`, {
            // Le « ← Retour » de la fiche revient aux Offres (pas à la home Runs par défaut).
            state: { from: "/offres" },
          }),
      },
    );

  return (
    <li className="flex flex-col gap-3 rounded-lg border border-border bg-surface-raised p-4 hover:border-border-strong sm:flex-row sm:items-center sm:justify-between sm:gap-4">
      <div className="min-w-0 flex-1">
        {candidateId ? (
          <button
            type="button"
            onClick={openFiche}
            disabled={evaluate.isPending}
            className="block w-full truncate text-left font-medium text-ink hover:underline disabled:opacity-60"
          >
            {offer.title}
          </button>
        ) : (
          <p className="truncate font-medium text-ink">{offer.title}</p>
        )}
        <p className="truncate text-sm text-ink-muted">
          {offer.company} · {offer.location} · {offer.contract_type} ·{" "}
          {formatDate(offer.created_at)}
        </p>
        {evaluate.isError && (
          <div className="mt-2">
            <ErrorNotice error={evaluate.error} />
          </div>
        )}
      </div>
      {/* Sur mobile : la ligne d'actions passe sous le titre, le score reste bien visible à droite. */}
      <div className="flex shrink-0 items-center justify-between gap-3 text-sm sm:justify-end">
        <div className="flex items-center gap-3">
          {offer.url && (
            <a
              href={offer.url}
              target="_blank"
              rel="noreferrer"
              className="text-ink-muted hover:text-ink hover:underline"
              title="Voir l'offre sur le site"
            >
              voir sur le site ↗
            </a>
          )}
          <span className="text-ink-muted">{offer.source}</span>
        </div>
        <ScoreBadge kind={offer.kind} score={offer.score} action={offer.action} />
      </div>
    </li>
  );
}

// Couleur du badge par bande de reco (seuils décidés côté serveur, cf. `RecommendationAction`).
const SCORE_TONES: Record<RecommendationAction, string> = {
  postuler: "bg-success/15 text-success-text",
  a_etudier: "bg-warning/15 text-warning-text",
  ignorer: "bg-ink/5 text-ink-muted",
};

/**
 * Badge de score de match. Une **formation** (OPP-166) n'est pas scorée : on affiche un badge
 * « Formation » explicite (jamais 0 ni le tiret ambigu). Sinon : la bande de reco colore le
 * score ; `null` (non ciblé / non évaluable pour un emploi) → tiret neutre.
 */
function ScoreBadge({
  kind,
  score,
  action,
}: {
  kind: OfferKind;
  score: number | null;
  action: RecommendationAction | null;
}) {
  if (kind === "formation") {
    return (
      <span
        className="rounded-full bg-brand/10 px-2 py-0.5 text-xs font-medium text-brand"
        title="Formation : non évaluée sur l'adéquation (son but est d'acquérir des compétences)"
      >
        Formation
      </span>
    );
  }
  if (score === null || action === null) {
    return <span className="text-ink-muted" title="Non évalué">—</span>;
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
