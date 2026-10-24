import type { AdvisoryStatus, DecisionStatus } from "../api/types";

// Libellés FR explicites — le front n'invente aucun statut hors contrat.
const ADVISORY_LABELS: Record<AdvisoryStatus, string> = {
  approved: "Pré-approuvé",
  pending: "En attente",
  rejected: "Pré-rejeté",
};

const DECISION_LABELS: Record<DecisionStatus, string> = {
  pending: "À décider",
  approved: "Approuvé",
  rejected: "Rejeté",
  deferred: "Reporté",
};

const TONE: Record<string, string> = {
  approved: "bg-success/15 text-success-text",
  rejected: "bg-danger/15 text-danger",
  pending: "bg-ink/5 text-ink",
  deferred: "bg-warning/15 text-warning-text",
};

// Ce que chaque badge REPRÉSENTE (OPP-149) : deux registres distincts, rappelés au survol
// et par la légende de la liste, pour lever la confusion « pré-évaluation vs décision ».
const KIND_TITLES: Record<"advisory" | "decision", string> = {
  advisory: "Pré-évaluation automatique",
  decision: "Décision humaine",
};

type Props =
  | { kind: "advisory"; value: AdvisoryStatus }
  | { kind: "decision"; value: DecisionStatus };

export function StatusBadge(props: Props) {
  const label =
    props.kind === "advisory" ? ADVISORY_LABELS[props.value] : DECISION_LABELS[props.value];
  return (
    <span
      title={KIND_TITLES[props.kind]}
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${TONE[props.value] ?? "bg-ink/5 text-ink"}`}
    >
      {label}
    </span>
  );
}
