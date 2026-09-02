// Comparaison d'une offre (informations clés issues d'offerKeyInfoExtractor)
// avec le profil candidat. Identifie les correspondances et les écarts,
// dimension par dimension : compétences, type de contrat, expérience, lieu,
// télétravail, langues, rémunération.
//
// Ne produit pas de score (cf. OPP-032) : seulement le constat structuré,
// exploité ensuite par le scoring et l'affichage. Réutilise le lexique partagé
// (skillLexicon) et les normalisateurs de l'extracteur (langues, télétravail),
// pour que les deux côtés parlent le même vocabulaire.
const { canonicalizeSkillName } = require("./skillLexicon");
const { extractLanguages, extractRemote } = require("./offerKeyInfoExtractor");

// --- Compétences -------------------------------------------------------------

// Compétences du profil (structuredSkills + skills legacy), canonisées vers le
// vocabulaire partagé, sans doublon. Les libellés non reconnus sont ignorés.
function profileSkillNames(profile) {
  const labels = [
    ...(profile.structuredSkills ?? []).map((skill) => skill?.name),
    ...(profile.skills ?? []),
  ];

  const names = new Set();
  for (const label of labels) {
    const canonical = canonicalizeSkillName(typeof label === "string" ? label : "");
    if (canonical) names.add(canonical);
  }
  return names;
}

// Correspondances / manques entre les compétences exigées par l'offre et celles
// du profil. `missing` = exigées par l'offre mais absentes du profil.
function compareSkills(offerSkills, profile) {
  const owned = profileSkillNames(profile);
  const matched = [];
  const missing = [];
  for (const skill of offerSkills) {
    (owned.has(skill) ? matched : missing).push(skill);
  }
  return { matched, missing };
}

// --- Type de contrat ---------------------------------------------------------

// Types d'offre acceptés selon le contrat recherché au profil. Normalise la
// divergence de casse : profil en minuscules (CDI/freelance/les deux), offre en
// majuscules (CDI/CDD/FREELANCE). Le CDD n'est visé par aucune préférence.
const PROFILE_CONTRACT_TO_OFFER = {
  cdi: ["CDI"],
  freelance: ["FREELANCE"],
  "les deux": ["CDI", "FREELANCE"],
};

function compareContractType(offerType, profile) {
  const profileType = profile.contractType;
  if (!offerType || !profileType) {
    return { offer: offerType ?? null, profile: profileType ?? null, compatible: null };
  }
  const accepted = PROFILE_CONTRACT_TO_OFFER[String(profileType).toLowerCase()] ?? [];
  return { offer: offerType, profile: profileType, compatible: accepted.includes(offerType) };
}

// --- Expérience --------------------------------------------------------------

// Confronte l'exigence d'expérience de l'offre au total d'années du profil
// (totalExperienceYears, déclaratif). « not_required » si l'offre n'exige rien ;
// « unknown » si le profil ne renseigne pas son total ; sinon « ok » / « insufficient ».
function compareExperience(requiredYears, profile = {}) {
  const owned = profile.totalExperienceYears ?? null;
  if (requiredYears == null) return { required: null, profile: owned, status: "not_required" };
  if (owned == null) return { required: requiredYears, profile: null, status: "unknown" };
  return { required: requiredYears, profile: owned, status: owned >= requiredYears ? "ok" : "insufficient" };
}

// --- Lieu --------------------------------------------------------------------

function normalizeText(value) {
  return typeof value === "string" && value.trim() !== "" ? value.trim().toLowerCase() : null;
}

// Marqueurs de forte mobilité géographique dans le champ libre profile.mobility.
const MOBILITY_MARKERS = /\bmobile\b|mobilit[ée]|france enti[èe]re|toute la france|partout|national|d[ée]placements?/i;

function isHighlyMobile(profile) {
  return typeof profile.mobility === "string" && MOBILITY_MARKERS.test(profile.mobility);
}

// Compare les lieux en tenant compte du contexte qui neutralise la contrainte :
// une offre en full remote, ou un profil géographiquement mobile, rend le lieu
// « non bloquant » (status "not_blocking" + `reason`) même en cas d'écart.
// Sinon : "match" / "mismatch" (deux lieux connus) ou "unknown".
function compareLocation(offerLocation, profile, offerRemote = null) {
  const base = { offer: offerLocation ?? null, profile: profile.location ?? null };

  // 1. Offre full remote : le lieu ne contraint pas.
  if (offerRemote === "remote") {
    return { ...base, status: "not_blocking", reason: "offer-remote" };
  }

  const offer = normalizeText(offerLocation);
  const prof = normalizeText(profile.location);

  // 2. Correspondance directe des lieux.
  if (offer && prof && (offer === prof || offer.includes(prof) || prof.includes(offer))) {
    return { ...base, status: "match", reason: null };
  }

  // 3. Profil mobile : couvre un écart ou une donnée de lieu manquante.
  if (isHighlyMobile(profile)) {
    return { ...base, status: "not_blocking", reason: "profile-mobility" };
  }

  // 4. Deux lieux connus mais différents.
  if (offer && prof) return { ...base, status: "mismatch", reason: null };

  // 5. Information insuffisante.
  return { ...base, status: "unknown", reason: null };
}

// --- Télétravail -------------------------------------------------------------

// Normalise le souhait du profil (texte libre) avec la même heuristique que
// l'offre, puis compare les modalités canoniques (remote/hybrid/onsite).
function compareRemote(offerRemote, profile) {
  const prof = profile.remote ? extractRemote(String(profile.remote)) : null;
  if (!offerRemote || !prof) {
    return { offer: offerRemote ?? null, profile: prof, status: "unknown" };
  }
  return { offer: offerRemote, profile: prof, status: offerRemote === prof ? "match" : "mismatch" };
}

// --- Langues -----------------------------------------------------------------

// Canonise les langues du profil via l'extracteur partagé (« English » →
// « anglais »), puis identifie correspondances et manques face à l'offre.
function compareLanguages(offerLanguages, profile) {
  const owned = new Set(extractLanguages((profile.languages ?? []).join(" ")));
  const matched = [];
  const missing = [];
  for (const lang of offerLanguages) {
    (owned.has(lang) ? matched : missing).push(lang);
  }
  return { matched, missing };
}

// --- Rémunération ------------------------------------------------------------

// Confronte la fourchette de l'offre à la cible du profil selon la période
// (annuel → targetSalary, jour → targetDailyRate). « ok » si l'offre peut
// atteindre la cible (max ≥ cible), « below » sinon, « unknown » si incomparable.
function compareSalary(offerSalary, profile) {
  if (!offerSalary) return { offer: null, target: null, status: "unknown" };

  const target =
    offerSalary.period === "day" ? profile.targetDailyRate
    : offerSalary.period === "year" ? profile.targetSalary
    : null;

  if (target == null) return { offer: offerSalary, target: null, status: "unknown" };
  return { offer: offerSalary, target, status: offerSalary.max >= target ? "ok" : "below" };
}

// --- Point d'entrée ----------------------------------------------------------

// Compare les informations clés d'une offre au profil et retourne le constat
// structuré, dimension par dimension.
function compareOfferToProfile(offerKeyInfo = {}, profile = {}) {
  return {
    skills: compareSkills(offerKeyInfo.skills ?? [], profile),
    contractType: compareContractType(offerKeyInfo.contractType ?? null, profile),
    experience: compareExperience(offerKeyInfo.experienceYears ?? null, profile),
    location: compareLocation(offerKeyInfo.location ?? null, profile, offerKeyInfo.remote ?? null),
    remote: compareRemote(offerKeyInfo.remote ?? null, profile),
    languages: compareLanguages(offerKeyInfo.languages ?? [], profile),
    salary: compareSalary(offerKeyInfo.salary ?? null, profile),
  };
}

module.exports = {
  compareOfferToProfile,
  compareSkills,
  compareContractType,
  compareExperience,
  compareLocation,
  compareRemote,
  compareLanguages,
  compareSalary,
};
