// Seuil de recommandation (OPP-035) : à partir du score d'adéquation (0-100),
// recommande automatiquement une action. Déterministe, seuils configurables.
const { scoreMatch } = require("./offerMatchScorer");

// Seuils par défaut (bornes basses incluses) : score ≥ high → postuler,
// score ≥ medium → à étudier, sinon → ignorer.
const DEFAULT_THRESHOLDS = { high: 75, medium: 50 };

// Actions recommandées : code stable (exploitable) + libellé affichable.
const RECOMMENDATIONS = {
  postuler: { action: "postuler", label: "Candidater" },
  a_etudier: { action: "a_etudier", label: "À étudier" },
  ignorer: { action: "ignorer", label: "Ignorer" },
};

// Recommande une action selon un score. Retourne { action, label, score }.
// Lève une erreur si le score n'est pas un nombre.
function recommendAction(score, thresholds = {}) {
  if (typeof score !== "number" || Number.isNaN(score)) {
    throw new Error("recommendAction : le score doit être un nombre");
  }
  const { high, medium } = { ...DEFAULT_THRESHOLDS, ...thresholds };

  const recommendation =
    score >= high ? RECOMMENDATIONS.postuler
    : score >= medium ? RECOMMENDATIONS.a_etudier
    : RECOMMENDATIONS.ignorer;

  return { ...recommendation, score };
}

// Raccourci : calcule le score d'un rapport de comparaison puis recommande.
function recommendForComparison(comparison, thresholds = {}) {
  return recommendAction(scoreMatch(comparison).score, thresholds);
}

module.exports = { DEFAULT_THRESHOLDS, RECOMMENDATIONS, recommendAction, recommendForComparison };
