// Score d'adéquation offre↔profil (OPP-032). Condense le rapport de comparaison
// (offerProfileComparator) en un score entier de 0 à 100.
//
// Principe : chaque dimension produit un sous-score [0,1] et porte un poids.
// Le score final est la moyenne pondérée, renormalisée sur les seules dimensions
// *évaluables* : une dimension « inconnue » (donnée manquante) est exclue du
// calcul plutôt que comptée comme nulle — on ne pénalise pas ce qu'on ignore.
const { compareOfferToProfile } = require("./offerProfileComparator");

// Poids relatifs des dimensions (les compétences priment ; le contrat pèse lourd
// car souvent rédhibitoire). Leur somme vaut 1 quand toutes sont évaluables.
const WEIGHTS = {
  skills: 0.35,
  contractType: 0.2,
  salary: 0.15,
  experience: 0.1,
  location: 0.1,
  remote: 0.05,
  languages: 0.05,
};

// Taux de couverture matched/(matched+missing), ou null si rien n'est exigé
// (dimension non discriminante → exclue du calcul).
function coverageScore({ matched = [], missing = [] } = {}) {
  const total = matched.length + missing.length;
  if (total === 0) return null;
  return matched.length / total;
}

// Sous-scores par dimension : 1 (favorable), 0 (défavorable), null (non évaluable).
function contractScore({ compatible } = {}) {
  if (compatible === true) return 1;
  if (compatible === false) return 0;
  return null;
}

function experienceScore({ status } = {}) {
  if (status === "ok") return 1;
  if (status === "insufficient") return 0;
  return null; // not_required, unknown
}

function locationScore({ status } = {}) {
  if (status === "match" || status === "not_blocking") return 1;
  if (status === "mismatch") return 0;
  return null; // unknown
}

function remoteScore({ status } = {}) {
  if (status === "match") return 1;
  if (status === "mismatch") return 0;
  return null; // unknown
}

function salaryScore({ status } = {}) {
  if (status === "ok") return 1;
  if (status === "below") return 0;
  return null; // unknown
}

// Calcule le score d'adéquation à partir d'un rapport de comparaison.
// Retourne { score, breakdown } : score ∈ [0,100] (entier), breakdown détaillant
// par dimension le sous-score (value), le poids et si elle a été évaluée.
function scoreMatch(comparison = {}) {
  const values = {
    skills: coverageScore(comparison.skills),
    contractType: contractScore(comparison.contractType),
    salary: salaryScore(comparison.salary),
    experience: experienceScore(comparison.experience),
    location: locationScore(comparison.location),
    remote: remoteScore(comparison.remote),
    languages: coverageScore(comparison.languages),
  };

  let weighted = 0;
  let totalWeight = 0;
  const breakdown = {};
  for (const [dimension, value] of Object.entries(values)) {
    const weight = WEIGHTS[dimension];
    const evaluated = value !== null;
    breakdown[dimension] = { value, weight, evaluated };
    if (evaluated) {
      weighted += value * weight;
      totalWeight += weight;
    }
  }

  const score = totalWeight === 0 ? 0 : Math.round((weighted / totalWeight) * 100);
  return { score, breakdown };
}

// Raccourci : compare l'offre au profil puis calcule le score.
function scoreOfferToProfile(offerKeyInfo, profile) {
  return scoreMatch(compareOfferToProfile(offerKeyInfo, profile));
}

module.exports = { WEIGHTS, scoreMatch, scoreOfferToProfile };
