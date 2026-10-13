import { useMemo } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Link, NavLink, Navigate, Route, Routes } from "react-router-dom";
import { createAuthAwareQueryClient } from "./api/queryClient";
import { useAuth } from "./auth/AuthContext";
import type { Me } from "./api/types";
import { LoginGate } from "./pages/LoginGate";
import { OffersPage } from "./pages/OffersPage";
import { RecommendationPage } from "./pages/RecommendationPage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { RunsListPage } from "./pages/RunsListPage";

/** Style d'un lien de nav : souligné + sombre quand actif, gris sinon. */
function navClass({ isActive }: { isActive: boolean }): string {
  return isActive
    ? "font-medium text-slate-900 underline underline-offset-4"
    : "text-slate-500 hover:text-slate-900";
}

export function App() {
  const { status, token, identity, logout, expireSession } = useAuth();

  // Plein-écran réservé à la **revérification au démarrage** d'un jeton stocké (`token`
  // déjà présent, encore en `checking`). Pendant un login interactif, `token` est null
  // tant que /me n'a pas répondu : on laisse la barrière afficher son état inline.
  if (status === "checking" && token) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">
        Vérification du jeton…
      </div>
    );
  }

  if (status !== "authenticated") return <LoginGate />;

  // Sous-arbre monté uniquement pendant une session authentifiée : le `QueryClient` y naît
  // et meurt avec la session (démonté au logout/expiration), garantissant un cache neuf par
  // session sans le recréer à chaque transition de `token`.
  return <AuthenticatedApp identity={identity} logout={logout} expireSession={expireSession} />;
}

function AuthenticatedApp({
  identity,
  logout,
  expireSession,
}: {
  identity: Me | null;
  logout: () => void;
  expireSession: () => void;
}) {
  // Un 401 sur n'importe quelle requête (lecture ou écriture) → fin de session : purge du
  // jeton et retour à la barrière de login, avec message d'expiration (cf. expireSession).
  const queryClient = useMemo(() => createAuthAwareQueryClient(expireSession), [expireSession]);

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="min-h-screen bg-slate-50 text-slate-900">
          <header className="border-b border-slate-200 bg-white">
            <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-3">
              <div className="flex items-center gap-6">
                <Link to="/" className="font-semibold">
                  Opportune — Hermes
                </Link>
                <nav className="flex items-center gap-4 text-sm">
                  <NavLink to="/" end className={navClass}>
                    Runs
                  </NavLink>
                  <NavLink to="/offres" className={navClass}>
                    Offres
                  </NavLink>
                </nav>
              </div>
              <div className="flex items-center gap-3 text-sm text-slate-500">
                {identity?.id && (
                  <span>
                    {identity.id}
                    {identity.role ? ` · ${identity.role}` : ""}
                  </span>
                )}
                <button onClick={logout} className="hover:text-slate-900">
                  Déconnexion
                </button>
              </div>
            </div>
          </header>
          <main className="mx-auto max-w-4xl px-4 py-6">
            <Routes>
              <Route path="/" element={<RunsListPage />} />
              <Route path="/offres" element={<OffersPage />} />
              <Route path="/runs/:runId" element={<RunDetailPage />} />
              <Route path="/recommendations/:id" element={<RecommendationPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
