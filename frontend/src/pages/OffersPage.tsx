import { useEffect, useRef } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useEvaluateOffer, useOffers } from "../api/offers";
import { useProfileReady } from "../api/profile";
import { CATALOG_STAGE_LABELS, isCatalogStage } from "../api/funnel";
import { useTargetCandidate } from "../api/useTargetCandidate";
import type { CatalogOffer, OfferKind, RecommendationAction } from "../api/types";
import { AddOffer } from "../components/AddOffer";
import { CollectOffers } from "../components/CollectOffers";
import { LaunchRun } from "../components/LaunchRun";
import { Pager } from "../components/Pager";
import { ProfileRequiredNotice } from "../components/ProfileRequiredNotice";
import { ErrorNotice, Loading } from "../components/States";
import { openExternal } from "../lib/openExternal";

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
  const { hash, key: locationKey } = useLocation();
  // Arrivée sur un ancrage (`/offres#nouvelle-analyse`, bouton du guide de démarrage) : on fait
  // défiler jusqu'au bloc, une seule fois par navigation (`key` de la location). Le bloc
  // n'apparaît qu'une fois la recherche active connue, d'où `target` dans les dépendances ; un
  // changement de recherche ensuite ne refait pas défiler (l'ancrage reste dans l'adresse).
  // Garde optionnel : `scrollIntoView` n'existe pas sous jsdom.
  const scrolledFor = useRef<string | null>(null);
  useEffect(() => {
    if (!hash || scrolledFor.current === locationKey) return;
    const block = document.getElementById(hash.slice(1));
    if (!block) return;
    scrolledFor.current = locationKey;
    block.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }, [hash, locationKey, target]);
  // Profil vierge (résolu) : la collecte et l'analyse sont grisées. Une seule invite au CV, en
  // tête de page, plutôt qu'une sous chacun des deux boutons (OPP-238).
  const profile = useProfileReady(target);
  const profileBlocked = target !== "" && !profile.ready && !profile.isPending;
  // Numéro de page porté par l'URL (`?page=`, OPP-239) : il survit à l'aller-retour vers une
  // fiche d'offre. Absent ou invalide → page 1 ; la page 1 n'est jamais écrite dans l'URL.
  const page = parsePage(searchParams.get("page"));
  const setPage = (next: number) =>
    setSearchParams(
      (prev) => {
        if (next <= 1) prev.delete("page");
        else prev.set("page", String(next));
        return prev;
      },
      { replace: true },
    );
  // Filtre par étape d'entonnoir, piloté par l'URL (clic sur une carte du cockpit, OPP-164).
  const rawStage = searchParams.get("stage");
  const stageFilter = isCatalogStage(rawStage) ? rawStage : null;
  // Bascule de recherche (sélecteur global) : on revient en page 1, sinon on resterait sur une
  // page hors bornes pour une recherche au catalogue plus court. On ne réagit qu'à un vrai
  // changement de recherche : ni au montage, ni au passage de « aucune » (résolution du
  // sélecteur au montage) à la recherche active, qui effaceraient la page lue dans l'URL.
  // On ne mémorise que les recherches non vides : A → « aucune » → B remet bien en page 1.
  const previousTarget = useRef(target);
  useEffect(() => {
    const previous = previousTarget.current;
    if (target) previousTarget.current = target;
    if (target && previous && previous !== target) setPage(1);
  }, [target]);
  // Filtrage **côté serveur** : le pool entier est filtré avant pagination, donc `total` et le
  // Pager concordent avec les compteurs du cockpit même au-delà d'une page.
  const { data, isPending, isError, error, isFetching, isPlaceholderData } = useOffers(
    page,
    target,
    stageFilter ?? "",
  );
  const items = data?.items ?? [];
  // Page au-delà de la dernière (favori `?page=50`, catalogue qui a diminué, recherche changée
  // depuis une autre page) : on se ramène sur la dernière page. On attend la vraie réponse,
  // pas les données de la page précédente affichées pendant le chargement.
  const lastPage = data ? Math.max(data.total_pages, 1) : null;
  useEffect(() => {
    if (lastPage !== null && !isPlaceholderData && page > lastPage) setPage(lastPage);
  }, [lastPage, isPlaceholderData, page]);

  const clearFilter = () => {
    setSearchParams(
      (prev) => {
        prev.delete("stage");
        prev.delete("page");
        return prev;
      },
      { replace: true },
    );
  };

  return (
    <section className="space-y-6">
      <h2 className="text-xl font-semibold text-ink">Offres</h2>

      {profileBlocked && (
        <ProfileRequiredNotice action="la collecte et l'analyse des offres" />
      )}

      <CollectOffers />

      {/* Actions sur le catalogue (OPP-238, auparavant sur l'Accueil) : analyser les offres
          pour la recherche active, ou en ajouter une à la main. */}
      <div className="grid gap-4 sm:grid-cols-2">
        {target !== "" && (
          <div
            id="nouvelle-analyse"
            className="flex flex-col gap-2 rounded-lg border border-border bg-surface-raised p-4"
          >
            <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">
              Nouvelle analyse
            </h3>
            <p className="text-sm text-ink-muted">
              Opportune passe en revue les offres de ton catalogue, les score pour ton profil
              et met en avant les plus pertinentes à étudier.
            </p>
            {/* Bouton ancré en bas : la carte s'aligne en hauteur sur « Ajouter une offre »,
                l'action reste au même niveau que son bouton voisin plutôt que de flotter. */}
            <div className="mt-auto pt-1">
              <LaunchRun showProfileNotice={false} />
            </div>
          </div>
        )}
        <AddOffer />
      </div>

      {/* La liste a son titre, comme « Dernières activités » sur l'Accueil (OPP-242). Le filtre
          actif et la liste restent groupés dessous, avec un espacement serré. */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">
          Bibliothèque d'offres
        </h3>
        {stageFilter && (
          <div className="flex items-center gap-2 text-sm">
            <span className="rounded-full bg-ink/5 px-3 py-1 text-ink">
              Filtré : {CATALOG_STAGE_LABELS[stageFilter]}
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
                ? `Aucune offre « ${CATALOG_STAGE_LABELS[stageFilter]} » pour cette recherche.`
                : "Aucune offre dans le catalogue. Récupère-en de nouvelles ou ajoute-en une ci-dessus."}
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
                onPrev={() => setPage(Math.max(1, page - 1))}
                onNext={() => setPage(page + 1)}
                busy={isFetching}
              />
            </div>
          ))}
      </div>
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
  const location = useLocation();
  const evaluate = useEvaluateOffer();

  const openFiche = () =>
    evaluate.mutate(
      { candidateId, offerId: offer.id },
      {
        onSuccess: (reco) =>
          navigate(`/recommendations/${encodeURIComponent(reco.recommendation_id)}`, {
            // Le « ← Retour » de la fiche revient à cette liste telle quelle : chemin, filtre
            // `?stage=` et page `?page=` (OPP-239), pas à la home par défaut.
            state: { from: location.pathname + location.search },
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
              onClick={(e) => {
                e.preventDefault();
                void openExternal(offer.url!);
              }}
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

/**
 * Lit `?page=` : suite de chiffres valant au moins 1, sinon page 1. La vérification stricte
 * écarte `1e21` ou `2.0`, que `Number` accepte mais que le back refuserait (400).
 */
function parsePage(raw: string | null): number {
  if (raw === null || !/^\d+$/.test(raw)) return 1;
  const n = Number(raw);
  return Number.isSafeInteger(n) && n >= 1 ? n : 1;
}

/** Formatage tolérant : valeur brute si la date n'est pas parsable. */
function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("fr-FR");
}
