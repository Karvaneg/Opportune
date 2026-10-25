import type { CollectionProgress } from "../api/types";

/**
 * Ligne de compteurs d'une collecte : « N collectée(s) · N nouvelle(s) · N doublon(s) »
 * (OPP-208). Fragment partagé par l'avancement local (`CollectProgress`) et l'indicateur
 * global (`CollectionBanner`) — libellé et pluralisation en un seul endroit. Chaque appelant
 * fournit son propre préfixe et son enveloppe (`span`, style).
 */
export function CollectCounts({ progress }: { progress: CollectionProgress }) {
  const { collected, stored, duplicates } = progress;
  return (
    <>
      {collected} collectée{collected > 1 ? "s" : ""} · {stored} nouvelle
      {stored > 1 ? "s" : ""} · {duplicates} doublon{duplicates > 1 ? "s" : ""}
    </>
  );
}
