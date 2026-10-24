import { useMemo } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Link, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Briefcase, History, Home, User, type LucideIcon } from "lucide-react";
import { createQueryClient } from "./api/queryClient";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { TargetCandidateProvider } from "./auth/useTargetCandidate";
import { useSpace } from "./space/SpaceContext";
import { WelcomeScreen } from "./space/WelcomeScreen";
import { DemoBanner } from "./space/DemoBanner";
import { SearchBar } from "./components/SearchBar";
import { Logo } from "./components/Logo";
import { ThemeToggle } from "./components/ThemeToggle";
import { CockpitPage } from "./pages/CockpitPage";
import { OffersPage } from "./pages/OffersPage";
import { ProfilePage } from "./pages/ProfilePage";
import { RecommendationPage } from "./pages/RecommendationPage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { RunsListPage } from "./pages/RunsListPage";

/** Onglets de navigation, partagés entre le header (desktop) et la barre du bas (mobile). */
const NAV_ITEMS: { to: string; label: string; end: boolean; icon: LucideIcon }[] = [
  { to: "/", label: "Accueil", end: true, icon: Home },
  { to: "/profil", label: "Profil", end: false, icon: User },
  { to: "/offres", label: "Offres", end: false, icon: Briefcase },
  { to: "/historique", label: "Historique", end: false, icon: History },
];

/**
 * N'affiche le sélecteur global que sur les pages du périmètre (accueil, profil, offres,
 * historique) — là où `target` pilote réellement l'affichage. Le masquer sur le détail d'un run
 * ou d'une recommandation (keyés par l'URL, pas par `target`) évite un sélecteur sans effet visible.
 */
function ScopeSearchBar() {
  const { pathname } = useLocation();
  const onScopePage =
    pathname === "/" ||
    ["/profil", "/offres", "/historique"].some((p) => pathname.startsWith(p));
  if (!onScopePage) return null;
  return (
    <div className="mb-6">
      <SearchBar />
    </div>
  );
}

/** Style d'un onglet du header (desktop) en « pill » : fond accent quand actif. */
function navClass({ isActive }: { isActive: boolean }): string {
  return isActive
    ? "rounded-md bg-brand/10 px-3 py-1.5 font-medium text-brand"
    : "rounded-md px-3 py-1.5 text-ink-muted transition-colors hover:bg-ink/5 hover:text-ink";
}

/** Style d'un onglet de la barre du bas (mobile) : pleine largeur, icône + label, accent si actif. */
function tabClass({ isActive }: { isActive: boolean }): string {
  return isActive
    ? "flex flex-1 flex-col items-center gap-0.5 py-2 text-xs font-medium text-brand"
    : "flex flex-1 flex-col items-center gap-0.5 py-2 text-xs text-ink-muted";
}

export function App() {
  const { space, chooseSpace } = useSpace();

  // Écran d'accueil (OPP-182) : tant qu'aucun espace n'est choisi, on propose « Mon espace »
  // ou « Démo ». Remplace l'ancien `LoginGate` — pas de login en local, juste le choix d'espace.
  if (!space) {
    return <WelcomeScreen onChoose={chooseSpace} />;
  }

  // `AuthProvider` **keyé par l'espace** : au changement d'espace il se remonte, donc `GET /me`
  // est resondé avec le bon en-tête `X-Opportune-Space` (identité/périmètre propres à l'espace)
  // et le cache React Query repart à zéro — aucune fuite de données d'un espace à l'autre.
  return (
    <AuthProvider key={space}>
      <BootGate />
    </AuthProvider>
  );
}

function BootGate() {
  const { status, retry } = useAuth();

  // Amorçage local (OPP-181) : on interroge `GET /me` au démarrage. Tant que l'API n'a pas
  // répondu, plein-écran neutre — plus de barrière de jeton.
  if (status === "checking") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface text-sm text-ink-muted">
        Chargement…
      </div>
    );
  }

  // API injoignable (serveur non lancé) : message clair + « Réessayer », pas un login.
  if (status === "error") {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-surface px-4 text-center">
        <div>
          <h1 className="text-lg font-bold tracking-tight text-ink">Opportune</h1>
          <p className="mt-2 max-w-sm text-sm text-ink-muted">
            L'API est injoignable. Vérifie que le serveur local est démarré
            (<code className="rounded bg-ink/5 px-1 py-0.5">bash scripts/serve-api.sh</code>),
            puis réessaie.
          </p>
        </div>
        <button
          onClick={retry}
          className="rounded-md bg-ink px-3 py-2 text-sm font-medium text-on-brand"
        >
          Réessayer
        </button>
      </div>
    );
  }

  return <AuthenticatedApp />;
}

function AuthenticatedApp() {
  const { space, resetSpace } = useSpace();
  // Cache créé une fois au montage (local-first : plus de cycle de session à gérer).
  const queryClient = useMemo(() => createQueryClient(), []);

  return (
    <QueryClientProvider client={queryClient}>
      <TargetCandidateProvider>
        <BrowserRouter>
          <div className="min-h-screen bg-surface text-ink">
            <header className="sticky top-0 z-10 border-b border-border bg-surface-raised/80 backdrop-blur">
              <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
                <div className="flex items-center gap-8">
                  <Link to="/" aria-label="Opportune, accueil" className="flex items-center">
                    <Logo height={32} />
                  </Link>
                  {/* Nav dans le header en desktop uniquement ; sur mobile elle passe en barre du bas. */}
                  <nav className="hidden items-center gap-1 text-sm sm:flex">
                    {NAV_ITEMS.map((item) => (
                      <NavLink key={item.to} to={item.to} end={item.end} className={navClass}>
                        {item.label}
                      </NavLink>
                    ))}
                  </nav>
                </div>
                <div className="flex items-center gap-2 text-sm text-ink-muted sm:gap-3">
                  {/* Espace actif (OPP-182) : pastille ambre en démo, neutre pour « Mon espace »,
                      + bouton pour revenir à l'accueil et changer d'espace. */}
                  <span
                    className={
                      space === "demo"
                        ? "rounded-full bg-warning/15 px-3 py-1 text-xs font-medium text-warning-text"
                        : "hidden rounded-full bg-ink/5 px-3 py-1 text-xs font-medium text-ink-muted sm:inline"
                    }
                  >
                    {space === "demo" ? "Démo" : "Mon espace"}
                  </span>
                  <button
                    onClick={resetSpace}
                    className="rounded-md px-2 py-1 text-xs font-medium text-ink-muted transition-colors hover:bg-ink/5 hover:text-ink"
                  >
                    Changer d'espace
                  </button>
                  <ThemeToggle />
                </div>
              </div>
            </header>
            {/* Bandeau démo (OPP-182) : repartir de zéro / restaurer l'exemple, espace démo uniquement. */}
            {space === "demo" && <DemoBanner />}
            {/* Padding bas sur mobile pour que le contenu ne passe pas sous la barre d'onglets fixe. */}
            <main className="mx-auto max-w-5xl px-4 pb-24 pt-6 sm:px-6 sm:pb-8 sm:pt-8">
              {/* Sélecteur global de recherche (OPP-184) : basculer / créer / renommer, partagé par
                  les pages du périmètre via le contexte de ciblage. En tête du contenu, sous la nav. */}
              <ScopeSearchBar />
              <Routes>
                <Route path="/" element={<CockpitPage />} />
                <Route path="/offres" element={<OffersPage />} />
                <Route path="/profil" element={<ProfilePage />} />
                <Route path="/historique" element={<RunsListPage />} />
                <Route path="/runs/:runId" element={<RunDetailPage />} />
                <Route path="/recommendations/:id" element={<RecommendationPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </main>
            {/* Barre d'onglets fixe en bas, mobile uniquement : accès au pouce, pattern « app ». */}
            <nav className="fixed inset-x-0 bottom-0 z-10 flex border-t border-border bg-surface-raised/95 pb-[env(safe-area-inset-bottom)] backdrop-blur sm:hidden">
              {NAV_ITEMS.map(({ to, label, end, icon: Icon }) => (
                <NavLink key={to} to={to} end={end} className={tabClass}>
                  <Icon className="h-5 w-5" aria-hidden />
                  {label}
                </NavLink>
              ))}
            </nav>
          </div>
        </BrowserRouter>
      </TargetCandidateProvider>
    </QueryClientProvider>
  );
}
