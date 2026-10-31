import { useState } from "react";
import { useRssSettings, useSaveRssSettings, type RssSettings as RssData } from "../api/settings";
import { useIsReviewer } from "../auth/roles";
import { ErrorNotice, Loading } from "./States";

/**
 * Réglage des flux RSS (OPP-195) : l'utilisateur colle les URLs des flux d'offres qu'il veut
 * suivre, une par ligne. La collecte RSS n'embarque aucun flux par défaut — faute de flux
 * d'offres FR gratuit et fiable — c'est donc la seule source de ces URLs. Reviewer uniquement
 * (curation du pool partagé, comme la collecte).
 *
 * Contrairement aux clés Adzuna, ces URLs ne sont **pas des secrets** : on les relit depuis l'API
 * et on les réaffiche telles quelles pour les éditer. Le back nettoie la liste (garde les
 * `http(s)` exploitables) et renvoie ce qu'il a réellement retenu — on resynchronise alors le
 * champ avec cette liste, pour que l'utilisateur voie exactement ce qui est enregistré.
 */
export function RssSettings() {
  const isReviewer = useIsReviewer();
  const { data, isPending, isError, error } = useRssSettings();

  if (!isReviewer) {
    return (
      <p className="rounded-md border border-dashed border-border bg-surface p-3 text-sm text-ink-muted">
        Un reviewer peut renseigner les flux RSS.
      </p>
    );
  }

  if (isPending) return <Loading label="Chargement des réglages…" />;
  if (isError) return <ErrorNotice error={error} />;

  // Monté avec les flux chargés : l'état local du champ part d'eux (sous-composant pour éviter une
  // resynchronisation manuelle au premier chargement).
  return <RssForm initialFeeds={data.feeds} />;
}

function RssForm({ initialFeeds }: { initialFeeds: string[] }) {
  const save = useSaveRssSettings();
  const [text, setText] = useState(initialFeeds.join("\n"));

  // Lignes non vides : ce qu'on envoie au back (qui filtrera lui-même les URLs non `http(s)`).
  const feeds = text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
  const configuredCount = initialFeeds.length;
  const canSave = feeds.length > 0 && !save.isPending;

  const submit = () =>
    save.mutate(
      { feeds },
      {
        // Resynchronise le champ avec la liste **réellement enregistrée** (après nettoyage back) :
        // une URL sans schéma `http(s)` disparaît, l'utilisateur le voit immédiatement.
        onSuccess: (saved: RssData) => setText(saved.feeds.join("\n")),
      },
    );

  return (
    <div className="space-y-4 rounded-lg border border-border bg-surface-raised p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">
          Flux RSS d'offres
        </h3>
        <span
          className={
            configuredCount > 0
              ? "rounded-full bg-success/15 px-3 py-1 text-xs font-medium text-success-text"
              : "rounded-full bg-ink/5 px-3 py-1 text-xs font-medium text-ink-muted"
          }
        >
          {configuredCount > 0
            ? `${configuredCount} flux configuré${configuredCount > 1 ? "s" : ""}`
            : "Aucun flux"}
        </span>
      </div>

      <div className="space-y-2 text-sm text-ink-muted">
        <p>
          Colle l'URL d'un flux RSS/Atom d'offres par ligne. La collecte « flux RSS » parcourt ces
          flux et ajoute les offres neuves au catalogue. Les flux ouverts fiables sont surtout
          orientés tech/remote (par ex.{" "}
          <a
            href="https://weworkremotely.com/remote-jobs.rss"
            target="_blank"
            rel="noreferrer"
            className="font-medium text-brand hover:underline"
          >
            We Work Remotely
          </a>
          ) ; la plupart des sites d'emploi français n'exposent plus de flux RSS public.
        </p>
      </div>

      <label className="block text-sm font-medium text-ink">
        URLs des flux (une par ligne)
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={5}
          spellCheck={false}
          placeholder="https://exemple.fr/offres.rss"
          aria-label="URLs des flux RSS"
          className="mt-1 block w-full rounded-md border border-border bg-surface px-3 py-2 font-mono text-sm text-ink"
        />
      </label>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={submit}
          disabled={!canSave}
          className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-on-brand hover:bg-brand-strong disabled:opacity-50"
        >
          {save.isPending ? "Enregistrement…" : "Enregistrer les flux"}
        </button>
        {save.isSuccess && (
          <span className="text-sm text-success-text">Flux RSS enregistrés.</span>
        )}
        {save.isError && <ErrorNotice error={save.error} />}
      </div>
    </div>
  );
}
