// Orchestrateur de candidature (OPP-087). Point d'intégration du MVP : à partir
// d'une offre normalisée (jobOffer) et d'un profil, déroule tout le pipeline de
// bout en bout et produit un dossier de décision — analyse, score, recommandation,
// risques — puis, pour une offre retenue, une candidature PERSISTÉE, scorée,
// documentée (documents versionnés) et suivie (relance planifiée).
//
// Le pipeline n'envoie jamais rien de lui-même : il prépare la candidature pour la
// validation humaine (cf. applicationSendGuard). Logique déterministe, sans LLM et
// sans nouvelle dépendance ; il se contente de composer les briques existantes :
//   extractKeyInfo → compareOfferToProfile → summarizeOffer (score/raisons/risques)
//   + classifyOpportunity, puis documentVersionService / applicationService /
//   followUpPlanner pour la persistance et le suivi.
const { extractKeyInfo } = require("./offerKeyInfoExtractor");
const { summarizeOffer } = require("./offerSummary");
const { classifyOpportunity } = require("./opportunityClassifier");
const { adaptResumeToOffer } = require("./resumeAdapter");
const { generateCoverLetter } = require("./coverLetterGenerator");
const { generateLinkedInMessage } = require("./linkedInMessageGenerator");
const { generateFreelanceProposal } = require("./freelanceProposalGenerator");
const { addVersion } = require("./documentVersionService");
const { saveValidApplication } = require("./applicationService");
const { planFollowUp } = require("./followUpPlanner");
const {
  DEFAULT_PATH: DEFAULT_APPLICATIONS_PATH,
} = require("../models/applicationStore");
const {
  DEFAULT_PATH: DEFAULT_DOCUMENTS_PATH,
} = require("../models/documentVersionStore");

// Action recommandée qui n'ouvre pas de candidature par défaut (cf. scoreRecommender).
const IGNORE_ACTION = "ignorer";

// Vrai si la valeur est une chaîne non vide (espaces seuls exclus).
function isNonEmptyString(value) {
  return typeof value === "string" && value.trim() !== "";
}

// Documents de candidature à générer pour une offre, fidèles au profil (aucune
// invention). Le CV adapté est toujours produit ; le document d'accroche et le
// message LinkedIn n'ont de sens que si l'entreprise et l'intitulé sont connus
// (mêmes garde-fous que les générateurs). Le document d'accroche est adapté au type
// de contrat : une offre FREELANCE reçoit une proposition d'intervention, les autres
// (CDI/CDD) une lettre de motivation. Retourne [{ type, content }], type ∈ DOCUMENT_TYPES.
function buildDocuments(offer, profile, keyInfo) {
  const documents = [
    { type: "cv", content: adaptResumeToOffer(profile, keyInfo) },
  ];

  if (isNonEmptyString(offer.company) && isNonEmptyString(offer.title)) {
    const pitch =
      offer.contractType === "FREELANCE"
        ? { type: "freelanceProposal", content: generateFreelanceProposal(profile, offer) }
        : { type: "coverLetter", content: generateCoverLetter(profile, offer) };
    documents.push(pitch);
    documents.push({ type: "linkedInMessage", content: generateLinkedInMessage(profile, offer) });
  }

  return documents;
}

// Décide si une offre doit déboucher sur une candidature persistée.
// - options.persist === true|false force la décision (utile pour un dry-run ou pour
//   candidater malgré une reco faible) ;
// - sinon : on persiste dès lors que la recommandation n'est pas « ignorer » et que
//   la catégorie n'est pas « À ignorer » (contrat hors préférences).
function shouldPersist(recommendationAction, category, persistOption) {
  if (persistOption === true || persistOption === false) return persistOption;
  return recommendationAction !== IGNORE_ACTION && category !== "À ignorer";
}

// Déroule le pipeline complet pour une offre normalisée confrontée à un profil.
//
// Options :
//   - persist            : force la création (true) ou l'inhibe (false) ; par défaut
//                          auto selon la recommandation et la catégorie ;
//   - followUp           : planifier une relance après création (défaut true) ;
//   - followUpDelayDays  : délai de la relance automatique (cf. followUpPlanner) ;
//   - applicationsPath   : store des candidatures (défaut applicationStore) ;
//   - documentsPath      : store des versions de documents (défaut documentVersionStore).
//
// Retourne un dossier : en-tête d'offre, keyInfo, catégorie, score, recommandation,
// raisons, risques, l'indicateur `persisted`, la candidature (ou null) et les
// versions de documents enregistrées (ou []).
function processOffer(offer = {}, profile = {}, options = {}) {
  const applicationsPath = options.applicationsPath ?? DEFAULT_APPLICATIONS_PATH;
  const documentsPath = options.documentsPath ?? DEFAULT_DOCUMENTS_PATH;

  // 1. Analyse (summarizeOffer compose extraction + comparaison + score + raisons).
  const keyInfo = extractKeyInfo(offer);
  const summary = summarizeOffer(offer, profile);
  const category = classifyOpportunity(offer, profile);

  const dossier = {
    offer: summary.offer,
    keyInfo,
    category,
    score: summary.score,
    recommendation: summary.recommendation,
    reasons: summary.reasons,
    risks: summary.risks,
    persisted: false,
    application: null,
    documents: [],
  };

  // 2. Décision : faut-il ouvrir une candidature ?
  if (!shouldPersist(summary.recommendation.action, category, options.persist)) {
    return dossier;
  }

  // 3. Documents versionnés (conservés, jamais écrasés — cf. documentVersionService).
  const documentVersions = buildDocuments(offer, profile, keyInfo).map((doc) =>
    addVersion({ offerId: offer.id, type: doc.type, content: doc.content }, documentsPath),
  );

  // 4. Candidature persistée, scorée, référençant ses documents.
  const application = saveValidApplication(
    {
      profileId: profile.id,
      offerId: offer.id,
      score: summary.score,
      nextAction: summary.recommendation.label,
      documents: documentVersions.map((v) => ({ type: v.type, ref: v.id, version: v.version })),
    },
    applicationsPath,
  );

  // 5. Suivi : relance planifiée (automatique).
  const persisted =
    options.followUp === false
      ? application
      : planFollowUp(application.id, { delayDays: options.followUpDelayDays }, applicationsPath);

  return { ...dossier, persisted: true, application: persisted, documents: documentVersions };
}

// Déroule le pipeline pour un lot d'offres (p. ex. sampleOffers()). Retourne la
// liste des dossiers, dans l'ordre des offres fournies.
function processOffers(offers = [], profile = {}, options = {}) {
  return offers.map((offer) => processOffer(offer, profile, options));
}

module.exports = { processOffer, processOffers };
