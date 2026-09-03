// Formatage du rapport de pipeline de candidature pour le terminal (OPP-088).
// Pur : renvoie du texte, n'écrit rien lui-même (aucun console.log), à l'image de
// display/tickets.js. Met en forme les dossiers produits par applicationPipeline
// (score, recommandation, catégorie, raisons, risques, candidature créée).

const DASH = "—";

// Pictogramme par action recommandée (cf. scoreRecommender).
const ACTION_ICON = {
  postuler: "✅",
  a_etudier: "🔎",
  ignorer: "⏭️",
};

// Une compétence peut être une chaîne ou un objet { name } ; on veut son libellé.
function skillLabel(skill) {
  return typeof skill === "string" ? skill : skill?.name ?? "";
}

// En-tête décrivant le profil de démonstration confronté aux offres.
function formatProfileHeader(profile = {}) {
  const name = profile.name || DASH;
  const contract = profile.contractType ? ` (${profile.contractType})` : "";
  const skills = (profile.skills ?? []).map(skillLabel).filter(Boolean).join(", ");
  const skillsLine = skills ? `\n   Compétences : ${skills}` : "";
  return `👤 Profil : ${name}${contract}${skillsLine}`;
}

// Ligne de statut de la candidature pour un dossier retenu.
function formatApplicationLine(dossier) {
  const app = dossier.application;
  const docs = `${dossier.documents.length} doc(s)`;
  const relance = app.followUpAt ? `, relance ${app.followUpAt}` : "";
  return `   📝 Candidature créée (${docs}${relance})`;
}

// Met en forme un dossier de pipeline : en-tête d'offre, ligne de décision,
// raisons positives/négatives, risques, et statut de candidature.
function formatDossier(dossier = {}) {
  const offer = dossier.offer ?? {};
  const title = offer.title || DASH;
  const company = offer.company || DASH;
  const reco = dossier.recommendation ?? {};
  const icon = ACTION_ICON[reco.action] ?? "•";

  const lines = [
    `━━━ ${title} — ${company}`,
    `   Score ${dossier.score}/100 · ${icon} ${reco.label ?? DASH} · Catégorie ${dossier.category ?? DASH}`,
  ];

  const positives = dossier.reasons?.positives ?? [];
  const negatives = dossier.reasons?.negatives ?? [];
  if (positives.length) lines.push(`   + ${positives.join("\n     ")}`);
  if (negatives.length) lines.push(`   - ${negatives.join("\n     ")}`);

  const risks = dossier.risks ?? [];
  if (risks.length) lines.push(`   ⚠ ${risks.join("\n     ")}`);

  lines.push(dossier.persisted ? formatApplicationLine(dossier) : "   ⏭️ Non retenue — aucune candidature créée");

  return lines.join("\n");
}

// Produit le rapport complet du pipeline : en-tête, récapitulatif, puis un bloc
// par offre analysée.
function formatPipelineReport(dossiers = [], { profile = {} } = {}) {
  const created = dossiers.filter((d) => d.persisted).length;

  const header = [
    "🚀 Opportune — démo du pipeline de candidature",
    formatProfileHeader(profile),
    "",
    `📊 ${dossiers.length} offre(s) analysée(s) · ${created} candidature(s) créée(s)`,
    "",
  ].join("\n");

  return [header, ...dossiers.map(formatDossier)].join("\n\n");
}

module.exports = { formatDossier, formatPipelineReport };
