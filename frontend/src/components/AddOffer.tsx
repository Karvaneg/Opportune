import { useState } from "react";
import { useAddOffer } from "../api/offers";
import { useIsReviewer } from "../auth/roles";
import { ErrorNotice } from "./States";

/**
 * Ajoute une offre au catalogue, par texte collé (OPP-145) ou par URL (OPP-148) — reviewer
 * uniquement (curation du pool partagé). Le back l'analyse via LLM (latence → « Ajout en
 * cours… »). Au succès, le catalogue est invalidé (cf. `useAddOffer`) : la nouvelle offre
 * apparaît dans l'onglet Offres. Raccourci du cockpit (OPP-164) — auparavant sur Offres (OPP-161).
 */
export function AddOffer() {
  const isReviewer = useIsReviewer();
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const add = useAddOffer();

  if (!isReviewer) return null;

  // Le texte prime (comme côté back) ; sinon on envoie l'URL. Un seul des deux suffit.
  const canSubmit = text.trim() !== "" || url.trim() !== "";
  const submit = () => {
    const variables = text.trim() !== "" ? { text } : { url };
    add.mutate(variables, {
      onSuccess: () => {
        setText("");
        setUrl("");
      },
    });
  };

  return (
    <div className="space-y-2 rounded-lg border border-border bg-surface-raised p-4">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">
        Ajouter une offre
      </h3>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Colle ici le texte d'une offre d'emploi…"
        rows={5}
        aria-label="Texte de l'offre"
        className="w-full rounded-md border border-border p-2 text-sm"
      />
      <div className="flex items-center gap-2">
        <span className="text-xs uppercase tracking-wide text-ink-muted">ou</span>
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://… (URL d'une offre)"
          aria-label="URL de l'offre"
          className="min-w-0 flex-1 rounded-md border border-border px-3 py-1.5 text-sm"
        />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={submit}
          disabled={add.isPending || !canSubmit}
          className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-on-brand hover:bg-brand-strong disabled:opacity-50"
        >
          {add.isPending ? "Ajout en cours…" : "Ajouter l'offre"}
        </button>
        {add.data && (
          <span className="text-sm text-success-text">
            Offre ajoutée : {add.data.title} — {add.data.company}. Elle apparaît dans
            l'onglet Offres.
          </span>
        )}
      </div>
      {add.isError && <ErrorNotice error={add.error} />}
    </div>
  );
}
