// Génération d'une lettre de motivation (OPP-041). Critère du ticket : la lettre
// mentionne précisément l'entreprise et l'offre.
//
// Approche par GABARIT, déterministe, sans dépendance ni LLM (cohérent avec le
// cap technique). La lettre n'invente rien : les variables proviennent de l'offre
// (entreprise, intitulé) et les compétences mises en avant du PROFIL réel, via
// l'adaptation fidèle (resumeAdapter → highlightedSkills). Aucune compétence
// exigée mais non détenue n'apparaît dans la lettre.
const { extractKeyInfo } = require("./offerKeyInfoExtractor");
const { adaptResumeToOffer } = require("./resumeAdapter");

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

// Phrase liée au type de contrat recherché au profil (null si non renseigné).
function contractSentence(contractType) {
  switch (contractType) {
    case "CDI":
      return "Je recherche aujourd'hui un poste en CDI.";
    case "freelance":
      return "Je suis disponible pour une mission en freelance.";
    case "les deux":
      return "Je suis ouvert(e) à une collaboration en CDI comme en freelance.";
    default:
      return null;
  }
}

// Génère une lettre de motivation pour un profil et une offre. Exige une
// entreprise et un intitulé de poste (sans quoi la lettre ne peut être précise) :
// lève une erreur explicite s'ils manquent. Retourne { subject, body,
// highlightedSkills } — body est la lettre en texte prêt à relire/envoyer.
function generateCoverLetter(profile = {}, offer = {}, options = {}) {
  if (!isNonEmptyString(offer.company) || !isNonEmptyString(offer.title)) {
    throw new Error(
      "L'entreprise et l'intitulé du poste sont requis pour une lettre précise",
    );
  }

  const company = offer.company.trim();
  const title = offer.title.trim();

  // Compétences réellement détenues et pertinentes pour l'offre (jamais inventées).
  const keyInfo = extractKeyInfo(offer);
  const { highlightedSkills } = adaptResumeToOffer(profile, keyInfo);

  const paragraphs = [
    "Madame, Monsieur,",
    `Je me permets de vous adresser ma candidature au poste de ${title} au sein de ${company}.`,
    highlightedSkills.length > 0
      ? `Mon parcours s'appuie notamment sur ${joinFr(highlightedSkills)}, en adéquation avec les attentes de votre offre.`
      : "Je suis convaincu(e) que mon parcours correspond aux attentes de votre offre.",
  ];

  const contract = contractSentence(profile.contractType);
  if (contract) paragraphs.push(contract);

  paragraphs.push(
    `Je me tiens à votre disposition pour un échange au sujet de ce poste chez ${company}.`,
    "Je vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées.",
  );
  if (isNonEmptyString(profile.name)) paragraphs.push(profile.name.trim());

  return {
    subject: `Candidature au poste de ${title} — ${company}`,
    body: paragraphs.join("\n\n"),
    highlightedSkills,
  };
}

module.exports = { generateCoverLetter };
