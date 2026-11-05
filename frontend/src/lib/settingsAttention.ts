import { useEffect, useState } from "react";

/**
 * Signal « attirer l'œil vers les Réglages » (OPP-227).
 *
 * Quand une action est désactivée faute d'un réglage (ex. clés Adzuna absentes), on fait
 * clignoter brièvement l'encadré qui l'explique et l'onglet « Réglages » du menu. Ces éléments
 * vivent dans des composants éloignés (page Offres et en-tête de l'app) : un événement `window`
 * les relie sans contexte React partagé.
 */
const SETTINGS_ATTENTION_EVENT = "opportune:settings-attention";

/** Demande aux éléments abonnés de clignoter une fois de plus. */
export function requestSettingsAttention(): void {
  window.dispatchEvent(new Event(SETTINGS_ATTENTION_EVENT));
}

/**
 * Nombre de demandes reçues depuis le montage (0 = aucune). S'en servir comme `key` de
 * l'élément à faire clignoter : changer la clé remonte l'élément, ce qui rejoue l'animation à
 * chaque nouvelle demande.
 */
export function useSettingsAttention(): number {
  const [requests, setRequests] = useState(0);
  useEffect(() => {
    const onRequest = () => setRequests((count) => count + 1);
    window.addEventListener(SETTINGS_ATTENTION_EVENT, onRequest);
    return () => window.removeEventListener(SETTINGS_ATTENTION_EVENT, onRequest);
  }, []);
  return requests;
}

/** Classe d'animation à appliquer tant qu'au moins une demande a été reçue. */
export function attentionClass(requests: number): string {
  return requests > 0 ? "motion-safe:animate-attention" : "";
}
