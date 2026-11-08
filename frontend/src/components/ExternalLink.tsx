import type { ReactNode } from "react";
import { openExternal } from "../lib/openExternal";

/**
 * Lien vers un site extérieur, ouvert dans le navigateur système, y compris depuis l'app de
 * bureau (cf. `openExternal`).
 *
 * `arrow` ajoute « ↗ » après le texte. La flèche est masquée au lecteur d'écran, pour que le
 * nom du lien reste son texte.
 */
export function ExternalLink({
  href,
  className,
  title,
  arrow = false,
  children,
}: {
  href: string;
  className?: string;
  title?: string;
  arrow?: boolean;
  children: ReactNode;
}) {
  return (
    <a
      href={href}
      onClick={(event) => {
        event.preventDefault();
        void openExternal(href);
      }}
      rel="noreferrer"
      className={className}
      title={title}
    >
      {children}
      {arrow && <span aria-hidden="true"> ↗</span>}
    </a>
  );
}
