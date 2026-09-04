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
  approved: "bg-emerald-100 text-emerald-800",
  rejected: "bg-red-100 text-red-800",
  pending: "bg-slate-100 text-slate-700",
  deferred: "bg-amber-100 text-amber-800",
};

type Props =
  | { kind: "advisory"; value: AdvisoryStatus }
  | { kind: "decision"; value: DecisionStatus };

export function StatusBadge(props: Props) {
  const label =
    props.kind === "advisory" ? ADVISORY_LABELS[props.value] : DECISION_LABELS[props.value];
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${TONE[props.value] ?? "bg-slate-100 text-slate-700"}`}
    >
      {label}
    </span>
  );
}
