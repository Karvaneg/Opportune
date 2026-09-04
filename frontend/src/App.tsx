import { useMemo } from "react";
import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Link, Navigate, Route, Routes } from "react-router-dom";
import { ApiHttpError } from "./api/client";
import { useAuth } from "./auth/AuthContext";
import { HomePage } from "./pages/HomePage";
import { LoginGate } from "./pages/LoginGate";
import { RunDetailPage } from "./pages/RunDetailPage";

export function App() {
  const { status, token, identity, logout } = useAuth();

  // Un 401 sur n'importe quelle requête → purge du jeton (retour à la barrière de login).
  const queryClient = useMemo(
    () =>
      new QueryClient({
        queryCache: new QueryCache({
          onError: (error) => {
            if (error instanceof ApiHttpError && error.status === 401) logout();
          },
        }),
        defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
      }),
    // Recréé à chaque changement de jeton → cache neuf par session : un nouveau login
    // (même erroné) ne réaffiche jamais les données mises en cache d'une session précédente.
    [token, logout],
  );

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

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="min-h-screen bg-slate-50 text-slate-900">
          <header className="border-b border-slate-200 bg-white">
            <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-3">
              <Link to="/" className="font-semibold">
                Opportune — Hermes
              </Link>
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
              <Route path="/" element={<HomePage />} />
              <Route path="/runs/:runId" element={<RunDetailPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
