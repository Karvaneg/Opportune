import { useCallback, useEffect, useState } from "react";
import { Monitor, Moon, Sun } from "lucide-react";

/**
 * Sélecteur de thème (OPP-185, tranche 3). Trois modes cyclés par un clic :
 *   auto → clair → sombre → auto.
 *
 * - « auto » suit le système (`prefers-color-scheme`) : clé localStorage **absente**. On résout
 *   la valeur système en JS et on la pose dans `data-theme` (un écouteur `matchMedia` la tient à
 *   jour tant qu'on reste en auto), si bien que `<html>` porte TOUJOURS un `data-theme` explicite.
 * - « clair »/« sombre » forcent via `data-theme`, écrit en localStorage pour persister.
 *
 * L'application au boot (anti-flash) est faite par le script inline d'`index.html`, qui lit
 * la même clé ; ce composant ne pilote que les changements et garde l'état en phase.
 */
type Theme = "auto" | "light" | "dark";

const STORAGE_KEY = "opportune.theme";
const ORDER: readonly Theme[] = ["auto", "light", "dark"];
const DARK_QUERY = "(prefers-color-scheme: dark)";

const META: Record<Theme, { icon: typeof Monitor; label: string }> = {
  auto: { icon: Monitor, label: "Thème : automatique (suit le système). Cliquer pour forcer le clair." },
  light: { icon: Sun, label: "Thème : clair. Cliquer pour forcer le sombre." },
  dark: { icon: Moon, label: "Thème : sombre. Cliquer pour revenir à l'automatique." },
};

function readStored(): Theme {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" ? value : "auto";
  } catch {
    return "auto";
  }
}

/** Valeur système courante (repli « light » si `matchMedia` indisponible). */
function systemTheme(): "light" | "dark" {
  return window.matchMedia?.(DARK_QUERY).matches ? "dark" : "light";
}

/** Applique le thème sur `<html>` : « auto » est résolu via le média système. */
function applyTheme(theme: Theme): void {
  const resolved = theme === "auto" ? systemTheme() : theme;
  document.documentElement.setAttribute("data-theme", resolved);
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(readStored);

  // En mode auto, suivre les bascules du système en direct (sans ça, un changement d'OS
  // ne serait pris en compte qu'au prochain chargement). Inactif dès qu'un thème est forcé.
  useEffect(() => {
    if (theme !== "auto") return;
    const mq = window.matchMedia?.(DARK_QUERY);
    if (!mq) return;
    const onChange = () => applyTheme("auto");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme]);

  const cycle = useCallback(() => {
    setTheme((prev) => {
      const next = ORDER[(ORDER.indexOf(prev) + 1) % ORDER.length];
      try {
        if (next === "auto") localStorage.removeItem(STORAGE_KEY);
        else localStorage.setItem(STORAGE_KEY, next);
      } catch {
        /* localStorage indisponible (mode privé strict) : le choix ne persiste pas, tant pis. */
      }
      applyTheme(next);
      return next;
    });
  }, []);

  const { icon: Icon, label } = META[theme];
  return (
    <button
      type="button"
      onClick={cycle}
      aria-label={label}
      title={label}
      className="rounded-md px-2 py-1 text-ink-muted transition-colors hover:bg-ink/5 hover:text-ink"
    >
      <Icon className="h-4 w-4" aria-hidden />
    </button>
  );
}
