import { useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";

/**
 * Barrière d'authentification MVP : saisie du jeton (OPP-100), **validé** via `GET /me`
 * (OPP-103) avant d'ouvrir la coquille — un jeton invalide est refusé ici, pas plus tard.
 */
export function LoginGate() {
  const { login, error, status } = useAuth();
  const [value, setValue] = useState("");
  const checking = status === "checking";

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    await login(value);
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm space-y-4 rounded-lg border border-slate-200 bg-white p-6 shadow-sm"
      >
        <div>
          <h1 className="flex items-baseline gap-2">
            <span className="text-lg font-bold tracking-tight text-slate-900">Opportune</span>
            <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-xs font-medium text-indigo-700">
              Hermes
            </span>
          </h1>
          <p className="mt-2 text-sm text-slate-500">
            Saisissez votre jeton d'accès pour consulter les runs.
          </p>
        </div>
        <label className="block text-sm font-medium text-slate-700">
          Jeton d'accès
          <input
            type="password"
            autoComplete="off"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Bearer token"
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
          />
        </label>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={value.trim().length === 0 || checking}
          className="w-full rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {checking ? "Vérification…" : "Continuer"}
        </button>
      </form>
    </div>
  );
}
