import { useEffect, useState } from "react";
import {
  useRequestUninstall,
  useUninstallInfo,
  type InstallKind,
  type UninstallInfo,
} from "../api/system";
import { formatBytes } from "../lib/formatBytes";
import { ExternalLink } from "./ExternalLink";
import { Modal } from "./Modal";
import { ErrorNotice } from "./States";

/**
 * Délai au bout duquel on considère que l'app de bureau n'a pas traité la demande. Elle regarde
 * la demande deux fois par seconde et se ferme en quelques secondes ; les suppressions qui
 * résistent sont réessayées pendant 5 s au plus.
 */
const CLOSE_TIMEOUT_MS = 20_000;

/** Documentation officielle d'Ollama pour le désinstaller sous Linux. */
const OLLAMA_LINUX_UNINSTALL_URL = "https://docs.ollama.com/linux#uninstall";

/**
 * Désinstallation depuis l'app (OPP-252). Proposée seulement dans l'app de bureau : c'est elle
 * qui arrête les services, supprime ce qui est coché et lance le désinstalleur du système.
 * Dans un navigateur (ou face à un back qui ne connaît pas la route), la section n'apparaît pas.
 */
export function UninstallSettings() {
  const { data } = useUninstallInfo();
  const [open, setOpen] = useState(false);

  if (!data?.available) return null;

  return (
    <div className="space-y-4 rounded-lg border border-border bg-surface-raised p-4">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">
        Désinstaller Opportune
      </h3>
      <p className="text-sm text-ink-muted">
        Retire Opportune de ton ordinateur. Tu choisis ce qui est supprimé avec l'app : le modèle
        d'IA qu'elle a téléchargé et tes données.
      </p>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-md border border-danger px-3 py-1.5 text-sm font-medium text-danger hover:bg-danger/10"
      >
        Désinstaller Opportune…
      </button>
      {open && <UninstallDialog info={data} onClose={() => setOpen(false)} />}
    </div>
  );
}

function UninstallDialog({ info, onClose }: { info: UninstallInfo; onClose: () => void }) {
  const request = useRequestUninstall();
  // Le modèle téléchargé par Opportune ne sert qu'à elle : coché par défaut. Les données sont
  // irremplaçables : la personne doit cocher elle-même.
  const [removeModel, setRemoveModel] = useState(info.model.removable);
  const [removeData, setRemoveData] = useState(false);

  if (request.isSuccess) {
    return <ClosingDialog info={info} choices={request.variables} onClose={onClose} />;
  }

  return (
    <Modal labelledBy="uninstall-title" onClose={onClose} className="max-w-lg">
      <div className="space-y-4 text-sm text-ink">
        <h2 id="uninstall-title" className="text-base font-semibold">
          Désinstaller Opportune
        </h2>

        <fieldset className="space-y-3">
          <legend className="font-medium">Que veux-tu supprimer ?</legend>

          {info.model.removable ? (
            <label className="flex items-start gap-2">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={removeModel}
                onChange={(event) => setRemoveModel(event.target.checked)}
              />
              <span>
                Le modèle d'IA téléchargé par Opportune (<code>{info.model.name}</code>
                {info.model.app_copy_bytes > 0 && `, ${formatBytes(info.model.app_copy_bytes)}`})
              </span>
            </label>
          ) : (
            info.model.present && (
              <p className="text-ink-muted">
                Le modèle d'IA <code>{info.model.name}</code> était déjà sur ton ordinateur avant
                Opportune : il est conservé.
              </p>
            )
          )}

          <label className="flex items-start gap-2">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={removeData}
              onChange={(event) => setRemoveData(event.target.checked)}
            />
            <span>
              Mes données Opportune : recherches, profils, offres, analyses, lettres, candidatures
              et réglages, espace Démo compris
            </span>
          </label>
          <p className="text-ink-muted">
            {removeData
              ? "Cette suppression est définitive. Si tu veux garder tes données, annule et exporte-les d'abord (« Sauvegarde de mes données »)."
              : "Ce que tu ne coches pas reste dans ce dossier :"}
            {!removeData && (
              <>
                {" "}
                <code className="break-all">{info.data_dir}</code>
              </>
            )}
          </p>
        </fieldset>

        <div className="space-y-2">
          <p className="font-medium">Ce qui se passe ensuite</p>
          <NextSteps kind={info.install_kind} appimagePath={info.appimage_path} />
        </div>

        {info.user_has_own_ollama && (
          <div className="space-y-1 rounded-md border border-border p-3 text-ink-muted">
            <p>
              Tu as aussi ton propre Ollama sur cet ordinateur. Opportune n'y touche pas.
            </p>
            <OwnOllamaHelp kind={info.install_kind} />
          </div>
        )}

        {request.isError && <ErrorNotice error={request.error} />}

        <div className="flex flex-wrap justify-end gap-3 pt-1">
          <button
            type="button"
            onClick={onClose}
            disabled={request.isPending}
            className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-ink hover:bg-ink/5 disabled:opacity-50"
          >
            Annuler
          </button>
          <button
            type="button"
            onClick={() => request.mutate({ remove_model: removeModel, remove_data: removeData })}
            disabled={request.isPending}
            className="rounded-md bg-danger px-3 py-1.5 text-sm font-medium text-on-brand hover:bg-danger-strong disabled:opacity-50"
          >
            {request.isPending ? "Désinstallation…" : "Désinstaller et fermer Opportune"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

/**
 * Après l'envoi de la demande : l'app doit se fermer toute seule. Si elle est encore là après
 * {@link CLOSE_TIMEOUT_MS}, on le dit et on rend la main, au lieu de laisser une fenêtre qu'on ne
 * peut pas fermer.
 */
function ClosingDialog({
  info,
  choices,
  onClose,
}: {
  info: UninstallInfo;
  choices: { remove_model: boolean; remove_data: boolean } | undefined;
  onClose: () => void;
}) {
  const [timedOut, setTimedOut] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setTimedOut(true), CLOSE_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, []);

  if (!timedOut) {
    return (
      <Modal labelledBy="uninstall-title" onClose={() => {}} className="max-w-lg">
        <h2 id="uninstall-title" className="text-base font-semibold text-ink">
          Désinstallation en cours
        </h2>
        <p className="mt-3 text-sm text-ink-muted">Opportune va se fermer dans un instant.</p>
      </Modal>
    );
  }

  const askedRemoval = choices?.remove_model || choices?.remove_data;
  return (
    <Modal labelledBy="uninstall-title" onClose={onClose} className="max-w-lg">
      <div className="space-y-3 text-sm text-ink">
        <h2 id="uninstall-title" className="text-base font-semibold">
          Opportune ne s'est pas fermée
        </h2>
        <p>
          La désinstallation n'a pas abouti. Ferme Opportune, puis retire-la par le moyen habituel
          de ton système.
        </p>
        {askedRemoval && (
          <p className="text-ink-muted">
            Ce que tu as coché n'a peut-être pas été supprimé. Tu peux le supprimer à la main dans
            ce dossier : <code className="break-all">{info.data_dir}</code>
          </p>
        )}
        <div className="flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-ink hover:bg-ink/5"
          >
            Fermer
          </button>
        </div>
      </div>
    </Modal>
  );
}

/** Marche à suivre après la fermeture de l'app, selon le type d'installation. */
function NextSteps({
  kind,
  appimagePath,
}: {
  kind: InstallKind | null;
  appimagePath: string | null;
}) {
  switch (kind) {
    case "windows-nsis":
      return <p>Opportune se ferme, puis le désinstalleur s'ouvre : suis ses étapes.</p>;
    case "windows-msi":
      return (
        <p>
          Opportune se ferme, puis la page « Applications installées » de Windows s'ouvre :
          choisis Opportune, puis « Désinstaller ».
        </p>
      );
    case "deb":
      return (
        <>
          <p>
            Opportune se ferme. Pour retirer l'app, lance ensuite cette commande dans un terminal
            (elle demande ton mot de passe) :
          </p>
          <CopyableCode text="sudo apt remove opportune" />
        </>
      );
    case "rpm":
      return (
        <>
          <p>
            Opportune se ferme. Pour retirer l'app, lance ensuite cette commande dans un terminal
            (elle demande ton mot de passe) :
          </p>
          <CopyableCode text="sudo rpm -e opportune" />
        </>
      );
    case "linux-other":
      return (
        <p>
          Opportune se ferme. Pour retirer l'app, désinstalle ensuite le paquet{" "}
          <code>opportune</code> avec le gestionnaire de paquets de ta distribution.
        </p>
      );
    case "appimage":
      return (
        <>
          <p>Opportune se ferme. Pour retirer l'app, supprime ensuite ce fichier :</p>
          {appimagePath && <CopyableCode text={appimagePath} />}
        </>
      );
    case "macos":
      return (
        <p>
          Opportune se ferme. Glisse ensuite Opportune du dossier « Applications » vers la
          corbeille.
        </p>
      );
    default:
      return (
        <p>
          Cette version est lancée depuis le code source : il n'y a pas d'app installée à retirer.
          Opportune se ferme après la suppression.
        </p>
      );
  }
}

/** Comment désinstaller l'Ollama personnel, selon le système. */
function OwnOllamaHelp({ kind }: { kind: InstallKind | null }) {
  if (kind === "windows-nsis" || kind === "windows-msi") {
    return (
      <p>
        Pour le désinstaller, ouvre « Applications installées » dans les paramètres de Windows,
        choisis Ollama, puis « Désinstaller ».
      </p>
    );
  }
  if (kind === "macos") {
    return <p>Pour le désinstaller, glisse Ollama du dossier « Applications » vers la corbeille.</p>;
  }
  return (
    <p>
      Pour le désinstaller, suis{" "}
      <ExternalLink href={OLLAMA_LINUX_UNINSTALL_URL} className="text-brand hover:underline" arrow>
        la documentation d'Ollama
      </ExternalLink>
      .
    </p>
  );
}

/** Texte à recopier (commande, chemin) avec un bouton « Copier ». */
function CopyableCode({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      // Presse-papiers refusé : le texte reste sélectionnable à la main.
      setCopied(false);
    }
  };

  return (
    <div className="flex items-start gap-2">
      <code className="flex-1 select-all break-all rounded-md bg-ink/5 px-2 py-1">{text}</code>
      <button
        type="button"
        onClick={copy}
        className="shrink-0 rounded-md border border-border px-2 py-1 text-xs font-medium text-ink hover:bg-ink/5"
      >
        {copied ? "Copié" : "Copier"}
      </button>
    </div>
  );
}
