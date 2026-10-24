import { Link, useNavigate } from "react-router-dom";
import { useCandidateActivity } from "../api/activity";
import { useCandidateStats } from "../api/stats";
import type { FunnelStage } from "../api/funnel";
import type { ActivityEvent } from "../api/types";
import { useTargetCandidate } from "../auth/useTargetCandidate";
import { AddOffer } from "../components/AddOffer";
import { LaunchRun } from "../components/LaunchRun";
import { NewProfileGuide } from "../components/NewProfileGuide";
import { ProfileSummaryCard } from "../components/ProfileSummaryCard";
import { ErrorNotice, Loading } from "../components/States";

/**
 * Cockpit — page d'accueil de synthèse (OPP-164). Répond à « qu'est-ce que je dois traiter
 * maintenant ? » : trois compteurs d'avancement (à étudier / à postuler / postulé) depuis
 * `GET /candidates/{id}/stats` (OPP-163), plus les raccourcis d'action (lancer une analyse,
 * ajouter une offre). Les deux premières cartes sont cliquables et ouvrent Offres pré-filtré
 * par action recommandée. Remplace l'ancien accueil « Runs », désormais sous « Historique ».
 */
export function CockpitPage() {
  // Recherche active pour les compteurs : sélection partagée (sélecteur global, OPP-184).
  const { target } = useTargetCandidate();
  const { data, isPending, isError, error } = useCandidateStats(target);

  return (
    <section className="space-y-6">
      <h2 className="text-xl font-semibold text-ink">Accueil</h2>

      {/* Guide d'accueil (OPP-177) : en tête de cockpit tant que la boucle de démarrage
          (CV → offres → analyse) n'est pas complète. Se masque de lui-même ensuite. */}
      {target !== "" && <NewProfileGuide candidateId={target} stats={data} />}

      {target === "" ? (
        <p className="rounded-lg border border-dashed border-border bg-surface-raised p-6 text-center text-sm text-ink-muted">
          Aucune recherche pour le moment.
        </p>
      ) : (
        <>
          {/* Profil en tête : « qui suis-je » avant « qu'ai-je à traiter ». Carte résumé compacte
              (détail sur l'onglet Profil) — on ne l'enterre plus sous le flux d'activité. */}
          <ProfileSummaryCard candidateId={target} />

          {/* Compteurs : la vue d'ensemble « qu'ai-je à traiter ? ». */}
          {isPending && <Loading label="Chargement de la synthèse…" />}
          {isError && <ErrorNotice error={error} />}
          {data && <StatCards stats={data} />}

          {/* Raccourcis d'action juste sous les compteurs : « que puis-je faire maintenant ? »
              reste visible au-dessus du flux d'activité (esprit d'OPP-165, retour dogfood). */}
          <div className="grid gap-4 sm:grid-cols-2">
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
                <LaunchRun />
              </div>
            </div>
            <AddOffer />
          </div>

          <ActivityFeed candidateId={target} />
        </>
      )}
    </section>
  );
}

/** Les trois compteurs d'avancement + le total du pool. */
function StatCards({
  stats,
}: {
  stats: { a_etudier: number; a_postuler: number; postule: number; offres_total: number };
}) {
  return (
    <div className="space-y-2">
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="À étudier"
          value={stats.a_etudier}
          stage="a_etudier"
          tone="bg-warning/10 text-warning-text hover:border-warning/30"
        />
        {/* Couleurs alignées sur le parcours de candidature de la fiche reco : « à postuler »
            reprend l'indigo de « intention de candidater notée », « postulées » le vert de
            « candidature effectuée » (c'est fait). */}
        <StatCard
          label="À postuler"
          value={stats.a_postuler}
          stage="a_postuler"
          tone="bg-brand/10 text-brand hover:border-brand/30"
        />
        <StatCard
          label="Postulées"
          value={stats.postule}
          stage="postule"
          tone="bg-success/10 text-success-text hover:border-success/30"
        />
      </div>
      <p className="text-sm text-ink-muted">{stats.offres_total} offre(s) au total</p>
    </div>
  );
}

/**
 * Flux « Dernière activité » (OPP-165) : journal transversal horodaté sous les cartes. Chaque
 * événement est un lien vers sa cible (fiche de recommandation, ou catalogue pour une offre).
 */
function ActivityFeed({ candidateId }: { candidateId: string }) {
  const { data, isPending, isError, error } = useCandidateActivity(candidateId);

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">
        Dernières activités
      </h3>
      {isPending && <Loading label="Chargement de l'activité…" />}
      {isError && <ErrorNotice error={error} />}
      {data &&
        (data.items.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border bg-surface-raised p-4 text-center text-sm text-ink-muted">
            Aucune activité récente.
          </p>
        ) : (
          <ul className="divide-y divide-border rounded-lg border border-border bg-surface-raised">
            {data.items.map((event, i) => (
              <li key={`${event.target_id}-${event.at}-${i}`} className="px-4 py-2.5">
                <ActivityRow event={event} />
              </li>
            ))}
          </ul>
        ))}
    </div>
  );
}

function ActivityRow({ event }: { event: ActivityEvent }) {
  const to =
    event.target_kind === "recommendation"
      ? `/recommendations/${encodeURIComponent(event.target_id)}`
      : "/offres";
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <Link
        to={to}
        state={{ from: "/" }}
        className="min-w-0 flex-1 truncate text-ink-muted hover:text-ink hover:underline"
      >
        {event.label}
      </Link>
      <span className="shrink-0 text-xs text-ink-muted">{formatActivityDate(event.at)}</span>
    </div>
  );
}

/** Date lisible ; valeur brute si non parsable (robustesse). */
function formatActivityDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("fr-FR");
}

/** Carte-compteur, cliquable : ouvre Offres filtré sur l'étape d'entonnoir. Le candidat ciblé est
 *  porté par le contexte partagé (cf. useTargetCandidate), inutile de le repasser par l'URL. */
function StatCard({
  label,
  value,
  stage,
  tone,
}: {
  label: string;
  value: number;
  stage: FunnelStage;
  tone: string;
}) {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() => navigate(`/offres?stage=${stage}`)}
      className={`rounded-lg border border-border p-4 text-left transition-colors ${tone}`}
    >
      <p className="text-3xl font-semibold">{value}</p>
      <p className="mt-1 text-sm font-medium">{label}</p>
    </button>
  );
}
