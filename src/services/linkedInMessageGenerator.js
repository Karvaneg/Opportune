// Génération d'un message LinkedIn (OPP-042). Deux variantes personnalisées pour
// une offre : une note de connexion courte (limite LinkedIn ≈ 300 caractères) et
// un message long type InMail.
//
// Approche par GABARIT, déterministe, sans dépendance ni LLM (cohérent avec le
// cap technique et avec coverLetterGenerator / OPP-041). Le message n'invente
// rien : l'entreprise et l'intitulé proviennent de l'offre, les compétences mises
// en avant proviennent du PROFIL réel via l'adaptation fidèle (resumeAdapter →
// highlightedSkills). Aucune compétence exigée mais non détenue n'y apparaît. Le
// champ highlightedSkills retourné est vérifiable par inventionGuard.verifyCoverLetter.
const { extractKeyInfo } = require("./offerKeyInfoExtractor");
const { adaptResumeToOffer } = require("./resumeAdapter");

// Longueur maximale d'une note de connexion LinkedIn (invitation).
const CONNECTION_NOTE_MAX_LENGTH = 300;

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

// Construit la note de connexion courte. La clause compétences n'est ajoutée que
// si le message reste sous la limite LinkedIn ; en dernier recours (intitulé /
// entreprise très longs) le message est tronqué proprement.
function buildConnectionNote({ name, title, company, skills }) {
  const intro = isNonEmptyString(name)
    ? `Bonjour, je suis ${name} et votre poste de ${title} chez ${company} a retenu mon attention.`
    : `Bonjour, votre poste de ${title} chez ${company} a retenu mon attention.`;
  const closing = "Seriez-vous ouvert(e) à un échange ?";

  if (skills.length > 0) {
    const withSkills = `${intro} Mon parcours s'appuie sur ${joinFr(skills)}. ${closing}`;
    if (withSkills.length <= CONNECTION_NOTE_MAX_LENGTH) return withSkills;
  }

  const base = `${intro} ${closing}`;
  if (base.length <= CONNECTION_NOTE_MAX_LENGTH) return base;

  // Dernier recours : tronquer sans couper au milieu d'un mot.
  const truncated = base.slice(0, CONNECTION_NOTE_MAX_LENGTH - 1);
  return `${truncated.slice(0, truncated.lastIndexOf(" ")).trimEnd()}…`;
}

// Construit le message long (InMail) : sujet + corps en paragraphes.
function buildInMail({ name, title, company, skills, contractType }) {
  const paragraphs = [
    "Bonjour,",
    `Je me permets de vous contacter au sujet du poste de ${title} chez ${company}.`,
    skills.length > 0
      ? `Mon parcours s'appuie notamment sur ${joinFr(skills)}, en adéquation avec les attentes de ce poste.`
      : "Je suis convaincu(e) que mon parcours correspond aux attentes de ce poste.",
  ];

  const contract = contractSentence(contractType);
  if (contract) paragraphs.push(contract);

  paragraphs.push(`Je serais ravi(e) d'échanger avec vous au sujet de cette opportunité chez ${company}.`);
  if (isNonEmptyString(name)) paragraphs.push(name.trim());

  return {
    subject: `Votre poste de ${title} chez ${company}`,
    body: paragraphs.join("\n\n"),
  };
}

// Génère les messages LinkedIn pour un profil et une offre. Exige une entreprise
// et un intitulé de poste (sans quoi le message ne peut être précis) : lève une
// erreur explicite s'ils manquent. Retourne { connectionNote, inMail,
// highlightedSkills, maxConnectionNoteLength }.
function generateLinkedInMessage(profile = {}, offer = {}) {
  if (!isNonEmptyString(offer.company) || !isNonEmptyString(offer.title)) {
    throw new Error(
      "L'entreprise et l'intitulé du poste sont requis pour un message précis",
    );
  }

  const company = offer.company.trim();
  const title = offer.title.trim();
  const name = isNonEmptyString(profile.name) ? profile.name.trim() : "";

  // Compétences réellement détenues et pertinentes pour l'offre (jamais inventées).
  const keyInfo = extractKeyInfo(offer);
  const { highlightedSkills } = adaptResumeToOffer(profile, keyInfo);

  return {
    connectionNote: buildConnectionNote({ name, title, company, skills: highlightedSkills }),
    inMail: buildInMail({ name, title, company, skills: highlightedSkills, contractType: profile.contractType }),
    highlightedSkills,
    maxConnectionNoteLength: CONNECTION_NOTE_MAX_LENGTH,
  };
}

module.exports = { generateLinkedInMessage, CONNECTION_NOTE_MAX_LENGTH };
