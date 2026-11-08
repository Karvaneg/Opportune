import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Fenêtre modale commune (OPP-246) : fond grisé, fenêtre centrée.
 *
 * - Rendue dans `document.body` (portail) : un parent qui crée son propre cadre de
 *   positionnement (ex. l'en-tête, `backdrop-blur`) enfermerait sinon la fenêtre `fixed`.
 * - Le focus va au premier élément focusable à l'ouverture, reste dans la fenêtre (Tab et
 *   Maj+Tab bouclent), puis revient à l'élément qui l'avait avant l'ouverture.
 * - Échap ferme. Un clic sur le fond ferme seulement si l'appui **et** le relâchement ont lieu
 *   sur le fond : une sélection de texte commencée dans la fenêtre et relâchée dehors ne ferme pas.
 *
 * Nommer la fenêtre par `label` (texte lu par le lecteur d'écran) ou par `labelledBy` (id d'un
 * titre visible dans `children`).
 */
export function Modal({
  label,
  labelledBy,
  onClose,
  className = "max-w-sm",
  children,
}: {
  label?: string;
  labelledBy?: string;
  onClose: () => void;
  /** Largeur de la fenêtre (classe Tailwind). */
  className?: string;
  children: ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const pressedOnBackdrop = useRef(false);
  // Toujours la dernière version d'`onClose`, sans rejouer l'effet (et donc le focus initial)
  // quand le parent passe une nouvelle fonction à chaque rendu.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const focusables = () =>
      Array.from(panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []);
    (focusables()[0] ?? panelRef.current)?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) {
        event.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      const outside = !panelRef.current?.contains(active);
      if (event.shiftKey && (active === first || outside)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || outside)) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previouslyFocused?.focus();
    };
  }, []);

  return createPortal(
    <div
      className="fixed inset-0 z-20 flex items-center justify-center bg-ink/30 p-4"
      onMouseDown={(event) => {
        pressedOnBackdrop.current = event.target === event.currentTarget;
      }}
      onClick={(event) => {
        if (pressedOnBackdrop.current && event.target === event.currentTarget) onClose();
        pressedOnBackdrop.current = false;
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        aria-labelledby={labelledBy}
        tabIndex={-1}
        className={`w-full ${className} rounded-lg bg-surface-raised p-5 shadow-lg`}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
