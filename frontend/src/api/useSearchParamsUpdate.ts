import { useLocation, useSearchParams } from "react-router-dom";

/**
 * Modifie les paramètres de l'adresse courante en une seule écriture (deux écritures
 * successives pourraient s'écraser), sans ajouter d'entrée à l'historique du navigateur. Le
 * `state` de navigation est conservé : il porte l'origine de la page, dont son lien retour a
 * besoin (OPP-240), et une réécriture de l'adresse l'effacerait sinon.
 */
export function useSearchParamsUpdate(): (change: (params: URLSearchParams) => void) => void {
  const [, setSearchParams] = useSearchParams();
  const { state } = useLocation();
  return (change) =>
    setSearchParams(
      (prev) => {
        change(prev);
        return prev;
      },
      { replace: true, state },
    );
}
