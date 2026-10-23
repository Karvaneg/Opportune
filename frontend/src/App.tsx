import { useMemo } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Link, NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Briefcase, History, Home, User, type LucideIcon } from "lucide-react";
import { createQueryClient } from "./api/queryClient";
import { useAuth } from "./auth/AuthContext";
import { TargetCandidateProvider } from "./auth/useTargetCandidate";
import type { Me } from "./api/types";
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

/** Style d'un onglet du header (desktop) en « pill » : fond accent quand actif. */
function navClass({ isActive }: { isActive: boolean }): string {
  return isActive
    ? "rounded-md bg-indigo-50 px-3 py-1.5 font-medium text-indigo-700"
    : "rounded-md px-3 py-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900";
}

/** Style d'un onglet de la barre du bas (mobile) : pleine largeur, icône + label, accent si actif. */
function tabClass({ isActive }: { isActive: boolean }): string {
  return isActive
    ? "flex flex-1 flex-col items-center gap-0.5 py-2 text-xs font-medium text-indigo-700"
    : "flex flex-1 flex-col items-center gap-0.5 py-2 text-xs text-slate-500";
}

export function App() {
  const { status, identity, retry } = useAuth();

  // Amorçage local (OPP-181) : on interroge `GET /me` au démarrage. Tant que l'API n'a pas
  // répondu, plein-écran neutre — plus de barrière de jeton.
  if (status === "checking") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">
        Chargement…
      </div>
    );
  }

  // API injoignable (serveur non lancé) : message clair + « Réessayer », pas un login.
  if (status === "error") {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-50 px-4 text-center">
        <div>
          <h1 className="text-lg font-bold tracking-tight text-slate-900">Opportune</h1>
          <p className="mt-2 max-w-sm text-sm text-slate-500">
            L'API est injoignable. Vérifie que le serveur local est démarré
            (<code className="rounded bg-slate-100 px-1 py-0.5">bash scripts/serve-api.sh</code>),
            puis réessaie.
          </p>
        </div>
        <button
          onClick={retry}
          className="rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white"
        >
          Réessayer
        </button>
      </div>
    );
  }

  return <AuthenticatedApp identity={identity} />;
}

function AuthenticatedApp({ identity }: { identity: Me | null }) {
  // Cache créé une fois au montage (local-first : plus de cycle de session à gérer).
  const queryClient = useMemo(() => createQueryClient(), []);

  return (
    <QueryClientProvider client={queryClient}>
      <TargetCandidateProvider>
        <BrowserRouter>
          <div className="min-h-screen bg-slate-50 text-slate-900">
            <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/80 backdrop-blur">
              <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
                <div className="flex items-center gap-8">
                  <Link to="/" className="text-lg font-bold tracking-tight text-slate-900">
                    Opportune
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
                <div className="flex items-center gap-2 text-sm text-slate-500 sm:gap-3">
                  {identity?.id && (
                    <span className="hidden rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600 sm:inline">
                      {identity.id}
                      {identity.role ? ` · ${identity.role}` : ""}
                    </span>
                  )}
                </div>
              </div>
            </header>
            {/* Padding bas sur mobile pour que le contenu ne passe pas sous la barre d'onglets fixe. */}
            <main className="mx-auto max-w-5xl px-4 pb-24 pt-6 sm:px-6 sm:pb-8 sm:pt-8">
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
            <nav className="fixed inset-x-0 bottom-0 z-10 flex border-t border-slate-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur sm:hidden">
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
