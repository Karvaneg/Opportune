// Explicabilité du score d'adéquation (OPP-033). Traduit le rapport de
// comparaison (offerProfileComparator) et le score (offerMatchScorer) en raisons
// lisibles, positives et négatives, exploitables pour l'affichage à l'utilisateur.
//
// Déterministe, sans LLM : chaque dimension produit 0 à 2 raisons (une positive
// et/ou une négative). Les dimensions non évaluables sont remontées séparément
// (unknown) pour la transparence. Les raisons sont triées par poids décroissant.
const { scoreMatch, WEIGHTS } = require("./offerMatchScorer");

// Énumération lisible : ["a","b"] → "a, b".
function list(items) {
  return items.join(", ");
}

// Constructeurs de raisons par dimension. Chacun retourne un tableau de
// { impact: "positive"|"negative"|"unknown", message }.
function skillReasons(skills = { matched: [], missing: [] }) {
  const reasons = [];
  if (skills.matched?.length) {
    reasons.push({ impact: "positive", message: `Compétences en adéquation : ${list(skills.matched)}` });
  }
  if (skills.missing?.length) {
    reasons.push({ impact: "negative", message: `Compétences attendues manquantes : ${list(skills.missing)}` });
  }
  return reasons;
}

function contractReasons(contract = {}) {
  if (contract.compatible === true) {
    return [{ impact: "positive", message: `Type de contrat compatible (${contract.offer})` }];
  }
  if (contract.compatible === false) {
    return [{ impact: "negative", message: `Type de contrat non désiré (offre ${contract.offer}, profil ${contract.profile})` }];
  }
  return [{ impact: "unknown", message: "Type de contrat non évalué" }];
}

function experienceReasons(experience = {}) {
  if (experience.status === "ok") {
    return [{ impact: "positive", message: `Expérience suffisante (${experience.profile} ans ≥ ${experience.required} requis)` }];
  }
  if (experience.status === "insufficient") {
    return [{ impact: "negative", message: `Expérience insuffisante (${experience.profile} ans < ${experience.required} requis)` }];
  }
  if (experience.status === "not_required") return []; // pas d'exigence → non discriminant
  return [{ impact: "unknown", message: "Expérience non évaluée (total du profil inconnu)" }];
}

function locationReasons(location = {}) {
  if (location.status === "match") {
    return [{ impact: "positive", message: `Lieu correspondant (${location.offer})` }];
  }
  if (location.status === "not_blocking") {
    const cause = location.reason === "offer-remote" ? "offre en télétravail total" : "profil mobile";
    return [{ impact: "positive", message: `Lieu non bloquant (${cause})` }];
  }
  if (location.status === "mismatch") {
    return [{ impact: "negative", message: `Lieu différent (offre ${location.offer}, profil ${location.profile})` }];
  }
  return [{ impact: "unknown", message: "Lieu non évalué" }];
}

function remoteReasons(remote = {}) {
  if (remote.status === "match") {
    return [{ impact: "positive", message: `Télétravail en adéquation (${remote.offer})` }];
  }
  if (remote.status === "mismatch") {
    return [{ impact: "negative", message: `Télétravail divergent (offre ${remote.offer}, profil ${remote.profile})` }];
  }
  return [{ impact: "unknown", message: "Télétravail non évalué" }];
}

function languageReasons(languages = { matched: [], missing: [] }) {
  const reasons = [];
  if (languages.matched?.length) {
    reasons.push({ impact: "positive", message: `Langues en adéquation : ${list(languages.matched)}` });
  }
  if (languages.missing?.length) {
    reasons.push({ impact: "negative", message: `Langues attendues manquantes : ${list(languages.missing)}` });
  }
  return reasons;
}

function salaryReasons(salary = {}) {
  if (salary.status === "ok") {
    return [{ impact: "positive", message: "Rémunération compatible avec la cible" }];
  }
  if (salary.status === "below") {
    return [{ impact: "negative", message: `Rémunération sous la cible (offre max ${salary.offer?.max}, cible ${salary.target})` }];
  }
  return [{ impact: "unknown", message: "Rémunération non évaluée" }];
}

const REASON_BUILDERS = {
  skills: skillReasons,
  contractType: contractReasons,
  salary: salaryReasons,
  experience: experienceReasons,
  location: locationReasons,
  remote: remoteReasons,
  languages: languageReasons,
};

// Explique un score d'adéquation à partir d'un rapport de comparaison.
// Retourne { score, breakdown, positives, negatives, unknown } — chaque raison
// est { dimension, weight, impact, message }, triée par poids décroissant.
function explainScore(comparison = {}) {
  const { score, breakdown } = scoreMatch(comparison);

  const all = [];
  for (const [dimension, build] of Object.entries(REASON_BUILDERS)) {
    for (const reason of build(comparison[dimension])) {
      all.push({ dimension, weight: WEIGHTS[dimension], ...reason });
    }
  }

  const byImpact = (impact) =>
    all.filter((reason) => reason.impact === impact).sort((a, b) => b.weight - a.weight);

  return {
    score,
    breakdown,
    positives: byImpact("positive"),
    negatives: byImpact("negative"),
    unknown: byImpact("unknown"),
  };
}

module.exports = { explainScore };
