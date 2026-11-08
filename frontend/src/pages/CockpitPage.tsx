import { Link, useNavigate } from "react-router-dom";
import { useCandidateActivity } from "../api/activity";
import { useCandidateStats } from "../api/stats";
import type { CatalogStage } from "../api/funnel";
import type { ActivityEvent } from "../api/types";
import { useTargetCandidate } from "../api/useTargetCandidate";
import { NewProfileGuide } from "../components/NewProfileGuide";
import { ProfileSummaryCard } from "../components/ProfileSummaryCard";
import { ScoringQualityCard } from "../components/ScoringQualityCard";
import { ErrorNotice, Loading } from "../components/States";

/**
 * Cockpit — page d'accueil de synthèse (OPP-164). Répond à « qu'est-ce que je dois traiter
 * maintenant ? » : trois compteurs d'avancement (à étudier / à postuler / postulé) depuis
 * `GET /candidates/{id}/stats` (OPP-163). Les actions sur les offres (lancer une analyse,
 * ajouter une offre) vivent sur la page Offres (OPP-238). Les deux premières cartes sont
 * cliquables et ouvrent Offres pré-filtré par action recommandée. Remplace l'ancien accueil « Runs », désormais sous « Historique ».
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
          Aucune recherche pour le moment. Crée une recherche ci-dessus pour commencer.
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

          {/* Qualité du score (OPP-234) : mes choix confirment-ils le score ? Sous les compteurs.
              Contrairement à eux, elle compte toutes mes décisions, y compris celles d'offres
              sorties du pool : ses totaux peuvent donc dépasser ceux des compteurs. */}
          <ScoringQualityCard candidateId={target} />

          <ActivityFeed candidateId={target} />
        </>
      )}
    </section>
  );
}

/** Les compteurs d'avancement (entonnoir + entretiens à venir + relances) + le total du pool. */
function StatCards({
  stats,
}: {
  stats: {
    a_etudier: number;
    a_postuler: number;
    postule: number;
    offres_total: number;
    entretiens_prevus: number;
    a_relancer: number;
  };
}) {
  return (
    <div className="space-y-2">
      <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-5">
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
        {/* Entretiens à venir (OPP-223) : filtre transverse « entretien » du catalogue (offres
            candidatées avec un entretien à venir). Teinte neutre, distincte des trois piles.
            `?? 0` : aucun entretien à venir (ou API antérieure à OPP-223) → 0, jamais vide. */}
        <StatCard
          label="Entretiens prévus"
          value={stats.entretiens_prevus ?? 0}
          stage="entretien"
          tone="bg-ink/5 text-ink hover:border-ink/20"
        />
        {/* Relances dues (OPP-235) : filtre transverse « a_relancer » du catalogue. Teinte
            danger : c'est une action en retard. `?? 0` : API antérieure à OPP-235 → 0. */}
        <StatCard
          label="À relancer"
          value={stats.a_relancer ?? 0}
          stage="a_relancer"
          tone="bg-danger/10 text-danger hover:border-danger/30"
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
        className="min-w-0 flex-1 truncate text-ink hover:underline"
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

/** Carte-compteur cliquable : ouvre Offres filtré sur l'étape/le filtre donné (le candidat ciblé
 *  vient du contexte partagé, cf. useTargetCandidate, inutile de le repasser par l'URL). */
function StatCard({
  label,
  value,
  stage,
  tone,
}: {
  label: string;
  value: number;
  stage: CatalogStage;
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
