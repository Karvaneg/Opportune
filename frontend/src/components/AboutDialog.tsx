import { useState } from "react";
import { CircleHelp, X } from "lucide-react";
import { APP_INFO } from "../lib/appInfo";
import { ExternalLink } from "./ExternalLink";
import { Modal } from "./Modal";

/**
 * Bouton « ? » de l'en-tête et fenêtre « À propos » (OPP-246) : version, licence, autrice,
 * liens vers son GitHub et vers le dépôt. Fermeture, focus et clavier : cf. `Modal`.
 */
export function AboutButton() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="À propos d'Opportune"
        title="À propos d'Opportune"
        className="rounded-md px-2 py-1 text-ink-muted transition-colors hover:bg-ink/5 hover:text-ink"
      >
        <CircleHelp className="h-4 w-4" aria-hidden />
      </button>
      {open && <AboutDialog onClose={() => setOpen(false)} />}
    </>
  );
}

const LINK_CLASS = "text-brand hover:underline";

function AboutDialog({ onClose }: { onClose: () => void }) {
  return (
    <Modal labelledBy="about-title" onClose={onClose} className="max-w-md">
      <div className="text-sm text-ink">
        <div className="flex items-start justify-between gap-4">
          <h2 id="about-title" className="text-base font-semibold">
            À propos d'{APP_INFO.name}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fermer"
            className="rounded-md p-1 text-ink-muted transition-colors hover:bg-ink/5 hover:text-ink"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>

        <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
          <dt className="text-ink-muted">Version</dt>
          <dd>v{APP_INFO.version}</dd>

          <dt className="text-ink-muted">Licence</dt>
          <dd>
            <ExternalLink href={APP_INFO.licenseUrl} className={LINK_CLASS} arrow>
              {APP_INFO.license}
            </ExternalLink>
          </dd>

          <dt className="text-ink-muted">Autrice</dt>
          <dd>
            <ExternalLink href={APP_INFO.authorUrl} className={LINK_CLASS} arrow>
              {APP_INFO.author}
            </ExternalLink>
          </dd>

          <dt className="text-ink-muted">Code source</dt>
          <dd>
            <ExternalLink href={APP_INFO.repoUrl} className={LINK_CLASS} arrow>
              github.com/Karvaneg/Opportune
            </ExternalLink>
          </dd>
        </dl>

        <p className="mt-4 text-xs text-ink-muted">
          © {APP_INFO.year} {APP_INFO.author}
        </p>
      </div>
    </Modal>
  );
}
