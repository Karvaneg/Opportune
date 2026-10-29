import { useState } from "react";
import { useAdzunaSettings, useSaveAdzunaSettings } from "../api/settings";
import { useIsReviewer } from "../auth/roles";
import { ErrorNotice, Loading } from "./States";

/**
 * Réglage des identifiants Adzuna (OPP-222) : l'utilisateur saisit ses propres `app_id` + `app_key`
 * (inscription gratuite sur developer.adzuna.com), que la collecte d'offres utilise ensuite — plus
 * de clés codées en dur ni d'environnement. Reviewer uniquement (saisie de secrets = curation,
 * comme la collecte).
 *
 * Les clés sont des **secrets** : l'API ne renvoie jamais leur valeur (seulement l'état
 * « configuré »), et on vide les champs après enregistrement pour ne pas les laisser traîner à
 * l'écran. Le champ `app_key` est masqué (type password).
 */
export function AdzunaSettings() {
  const isReviewer = useIsReviewer();
  const { data, isPending, isError, error } = useAdzunaSettings();
  const save = useSaveAdzunaSettings();
  const [appId, setAppId] = useState("");
  const [appKey, setAppKey] = useState("");

  if (!isReviewer) {
    return (
      <p className="rounded-md border border-dashed border-border bg-surface p-3 text-sm text-ink-muted">
        Un reviewer peut renseigner les clés Adzuna.
      </p>
    );
  }

  if (isPending) return <Loading label="Chargement des réglages…" />;
  if (isError) return <ErrorNotice error={error} />;

  const canSave = appId.trim() !== "" && appKey.trim() !== "" && !save.isPending;

  const submit = () =>
    save.mutate(
      { appId: appId.trim(), appKey: appKey.trim() },
      {
        // On vide les champs au succès : un secret ne doit pas rester dans l'état ni le DOM
        // au-delà de l'enregistrement. L'état « configuré » (relu) confirme la prise en compte.
        onSuccess: () => {
          setAppId("");
          setAppKey("");
        },
      },
    );

  return (
    <div className="space-y-4 rounded-lg border border-border bg-surface-raised p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">
          Clés API Adzuna
        </h3>
        <span
          className={
            data?.configured
              ? "rounded-full bg-success/15 px-3 py-1 text-xs font-medium text-success-text"
              : "rounded-full bg-ink/5 px-3 py-1 text-xs font-medium text-ink-muted"
          }
        >
          {data?.configured ? "Configurées" : "Non configurées"}
        </span>
      </div>

      <p className="text-sm text-ink-muted">
        La collecte d'offres interroge Adzuna avec tes propres clés. Crée un compte gratuit sur{" "}
        <a
          href="https://developer.adzuna.com"
          target="_blank"
          rel="noreferrer"
          className="font-medium text-brand hover:underline"
        >
          developer.adzuna.com
        </a>{" "}
        pour obtenir ton <code className="rounded bg-ink/5 px-1 py-0.5">app_id</code> et ta{" "}
        <code className="rounded bg-ink/5 px-1 py-0.5">app_key</code>. Elles sont stockées
        localement sur ta machine, jamais envoyées ailleurs.
      </p>

      <div className="space-y-3">
        <label className="block text-sm font-medium text-ink">
          App ID
          <input
            type="text"
            value={appId}
            onChange={(e) => setAppId(e.target.value)}
            autoComplete="off"
            placeholder={data?.configured ? "•••••••• (laisser pour conserver)" : "Ton app_id Adzuna"}
            aria-label="App ID Adzuna"
            className="mt-1 block w-full rounded-md border border-border bg-surface px-3 py-1.5 text-sm text-ink"
          />
        </label>
        <label className="block text-sm font-medium text-ink">
          App Key
          <input
            type="password"
            value={appKey}
            onChange={(e) => setAppKey(e.target.value)}
            autoComplete="off"
            placeholder={data?.configured ? "•••••••• (laisser pour conserver)" : "Ta app_key Adzuna"}
            aria-label="App Key Adzuna"
            className="mt-1 block w-full rounded-md border border-border bg-surface px-3 py-1.5 text-sm text-ink"
          />
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={submit}
          disabled={!canSave}
          className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-on-brand hover:bg-brand-strong disabled:opacity-50"
        >
          {save.isPending ? "Enregistrement…" : "Enregistrer les clés"}
        </button>
        {save.isSuccess && (
          <span className="text-sm text-success-text">Clés Adzuna enregistrées.</span>
        )}
        {save.isError && <ErrorNotice error={save.error} />}
      </div>
    </div>
  );
}
