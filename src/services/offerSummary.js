// Résumé d'une offre pour la validation humaine (OPP-051). Compose l'ensemble du
// pipeline en un dossier de décision contenant, comme l'exige le ticket : le
// score, les raisons, les risques et les documents.
//
// - raisons  : le « pourquoi » du score (positives / négatives), via scoreExplainer ;
// - risques  : les points d'attention avant de candidater — contraintes de l'offre,
//              compétences exigées non détenues, contrat non désiré ;
// - documents: les pièces générées pour l'offre (CV adapté, lettre), fidèles au profil.
const { extractKeyInfo } = require("./offerKeyInfoExtractor");
const { compareOfferToProfile } = require("./offerProfileComparator");
const { explainScore } = require("./scoreExplainer");
const { recommendAction } = require("./scoreRecommender");
const { adaptResumeToOffer } = require("./resumeAdapter");
const { generateCoverLetter } = require("./coverLetterGenerator");

// Vrai si la valeur est une chaîne non vide.
function isNonEmptyString(value) {
  return typeof value === "string" && value.trim() !== "";
}

// Risques à signaler avant de candidater, à partir de la comparaison et des
// informations clés de l'offre.
function collectRisks(comparison, keyInfo) {
  const risks = [];

  if (comparison.contractType?.compatible === false) {
    risks.push(`Type de contrat non désiré (offre ${comparison.contractType.offer}, profil ${comparison.contractType.profile})`);
  }
  for (const skill of comparison.skills?.missing ?? []) {
    risks.push(`Compétence exigée non détenue : ${skill}`);
  }
  for (const constraint of keyInfo.constraints ?? []) {
    risks.push(`Contrainte de l'offre : ${constraint}`);
  }

  return risks;
}

// Documents générés pour l'offre (fidèles au profil). La lettre n'est produite
// que si l'entreprise et l'intitulé sont connus (cf. coverLetterGenerator).
function collectDocuments(offer, profile, keyInfo) {
  const adapted = adaptResumeToOffer(profile, keyInfo);
  const documents = [
    {
      type: "CV adapté",
      highlightedSkills: adapted.highlightedSkills,
      missingSkills: adapted.missingSkills,
    },
  ];

  if (isNonEmptyString(offer.company) && isNonEmptyString(offer.title)) {
    const letter = generateCoverLetter(profile, offer);
    documents.push({ type: "Lettre de motivation", subject: letter.subject });
  }

  return documents;
}

// Construit le résumé d'une offre confrontée à un profil : en-tête, score,
// recommandation, raisons (positives/négatives), risques et documents.
function summarizeOffer(offer = {}, profile = {}) {
  const keyInfo = extractKeyInfo(offer);
  const comparison = compareOfferToProfile(keyInfo, profile);
  const explanation = explainScore(comparison);

  return {
    offer: {
      title: offer.title ?? null,
      company: offer.company ?? null,
      contractType: offer.contractType ?? null,
      location: offer.location ?? null,
    },
    score: explanation.score,
    recommendation: recommendAction(explanation.score),
    reasons: {
      positives: explanation.positives.map((r) => r.message),
      negatives: explanation.negatives.map((r) => r.message),
    },
    risks: collectRisks(comparison, keyInfo),
    documents: collectDocuments(offer, profile, keyInfo),
  };
}

module.exports = { summarizeOffer };
