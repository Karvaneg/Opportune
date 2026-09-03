// Génération d'une proposition freelance (OPP-043). Pendant « mission » de la
// lettre de motivation (OPP-041) et du message LinkedIn (OPP-042) : produit une
// proposition commerciale adressée au client pour une mission, mentionnant
// précisément la mission et le client, les compétences pertinentes et les
// conditions d'intervention (TJM, disponibilité, durée).
//
// Approche par GABARIT, déterministe, sans dépendance ni LLM (cohérent avec le cap
// technique). La proposition n'invente RIEN : la mission et le client viennent de
// l'offre, les compétences mises en avant du PROFIL réel via l'adaptation fidèle
// (resumeAdapter → highlightedSkills), et les conditions du profil (targetDailyRate,
// availability) et de la mission (durée). Aucune compétence exigée mais non détenue
// n'apparaît. highlightedSkills est vérifiable par inventionGuard.verifyCoverLetter.
const { extractKeyInfo } = require("./offerKeyInfoExtractor");
const { adaptResumeToOffer } = require("./resumeAdapter");
const { extractFreelanceDetails } = require("./offerFreelanceConnector");

// Vrai si la valeur est une chaîne non vide (espaces seuls exclus).
function isNonEmptyString(value) {
  return typeof value === "string" && value.trim() !== "";
}

// Énumération française : ["a","b","c"] → "a, b et c".
function joinFr(items) {
  if (items.length === 0) return "";
  if (items.length === 1) return items[0];
  return `${items.slice(0, -1).join(", ")} et ${items[items.length - 1]}`;
}

// Conditions d'intervention proposées, à partir du profil (TJM cible, disponibilité)
// et de la mission (durée). Chaque condition est null si l'information est absente
// — on ne propose jamais une valeur inventée.
function collectTerms(profile, offer) {
  const missionDetails = offer.freelance ?? extractFreelanceDetails(offer.raw ?? {});
  return {
    dailyRate: typeof profile.targetDailyRate === "number" ? profile.targetDailyRate : null,
    availability: isNonEmptyString(profile.availability) ? profile.availability.trim() : null,
    duration: isNonEmptyString(missionDetails.duration) ? missionDetails.duration.trim() : null,
  };
}

// Phrase récapitulant les conditions d'intervention connues (null si aucune).
function termsSentence({ dailyRate, availability, duration }) {
  const parts = [];
  if (dailyRate != null) parts.push(`un tarif journalier de ${dailyRate} € (TJM)`);
  if (availability) parts.push(`une disponibilité ${availability}`);
  if (duration) parts.push(`pour une mission d'une durée de ${duration}`);
  if (parts.length === 0) return null;
  return `Je vous propose ${joinFr(parts)}.`;
}

// Génère une proposition freelance pour un profil et une mission. Exige un client
// (entreprise) et un intitulé de mission (sans quoi la proposition ne peut être
// précise) : lève une erreur explicite s'ils manquent. Retourne { subject, body,
// highlightedSkills, terms } — body est la proposition en texte prêt à relire/envoyer.
function generateFreelanceProposal(profile = {}, offer = {}, options = {}) {
  if (!isNonEmptyString(offer.company) || !isNonEmptyString(offer.title)) {
    throw new Error(
      "Le client et l'intitulé de la mission sont requis pour une proposition précise",
    );
  }

  const client = offer.company.trim();
  const mission = offer.title.trim();

  // Compétences réellement détenues et pertinentes pour la mission (jamais inventées).
  const keyInfo = extractKeyInfo(offer);
  const { highlightedSkills } = adaptResumeToOffer(profile, keyInfo);
  const terms = collectTerms(profile, offer);

  const paragraphs = [
    "Madame, Monsieur,",
    `Je vous adresse ma proposition d'intervention pour la mission de ${mission} au sein de ${client}.`,
    highlightedSkills.length > 0
      ? `Mon expertise s'appuie notamment sur ${joinFr(highlightedSkills)}, en adéquation avec les besoins de votre mission.`
      : "Je suis convaincu(e) que mon expertise correspond aux besoins de votre mission.",
  ];

  const conditions = termsSentence(terms);
  if (conditions) paragraphs.push(conditions);

  paragraphs.push(
    `Je me tiens à votre disposition pour échanger sur les modalités de cette mission chez ${client}.`,
    "Je vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées.",
  );
  if (isNonEmptyString(profile.name)) paragraphs.push(profile.name.trim());

  return {
    subject: `Proposition pour la mission de ${mission} — ${client}`,
    body: paragraphs.join("\n\n"),
    highlightedSkills,
    terms,
  };
}

module.exports = { generateFreelanceProposal };
