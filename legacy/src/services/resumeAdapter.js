// Adaptation d'un CV à une offre (OPP-040). Contrainte forte (critère du ticket) :
// le CV adapté reste STRICTEMENT fidèle au profil réel — aucune invention.
//
// Le CV importé (resume.extractedText) est du texte brut non structuré : le
// régénérer exigerait un LLM et risquerait d'inventer. La source de vérité
// structurée est donc le PROFIL. L'adaptation se limite à *sélectionner* et
// *réordonner* des éléments existants du profil (compétences, expériences,
// langues) en fonction des informations clés de l'offre (offerKeyInfoExtractor),
// et à *signaler* les manques sans jamais les ajouter au CV. Déterministe, sans
// dépendance, sans LLM — cohérent avec la vérification anti-invention (OPP-044).
const { canonicalizeSkillName, findSkillsInText } = require("./skillLexicon");

// Compétences du profil unifiées (structuredSkills + skills legacy), dédupliquées
// par nom (insensible à la casse), en conservant le libellé d'origine (fidélité).
function collectProfileSkills(profile) {
  const labels = [
    ...(profile.structuredSkills ?? []).map((skill) => skill?.name),
    ...(profile.skills ?? []),
  ].filter((name) => typeof name === "string" && name.trim() !== "");

  const seen = new Set();
  const out = [];
  for (const label of labels) {
    const name = label.trim();
    const key = name.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ name });
  }
  return out;
}

// Réordonne les compétences du profil : celles attendues par l'offre d'abord
// (dans l'ordre de pertinence de l'offre), le reste ensuite dans l'ordre d'origine.
// Marque les compétences mises en avant. N'ajoute ni ne retire aucune compétence.
function tailorSkills(profile, offerSkills) {
  const offerIndex = new Map(offerSkills.map((skill, i) => [skill, i]));

  const enriched = collectProfileSkills(profile).map(({ name }, order) => {
    const canonical = canonicalizeSkillName(name);
    const rank = canonical != null && offerIndex.has(canonical) ? offerIndex.get(canonical) : Infinity;
    return { name, canonical, highlighted: rank !== Infinity, rank, order };
  });

  enriched.sort((a, b) => {
    if (a.rank !== b.rank) {
      if (a.rank === Infinity) return 1;
      if (b.rank === Infinity) return -1;
      return a.rank - b.rank;
    }
    return a.order - b.order;
  });

  const skills = enriched.map(({ name, canonical, highlighted }) => ({ name, canonical, highlighted }));
  const owned = new Set(enriched.map((entry) => entry.canonical).filter(Boolean));

  return {
    skills,
    highlightedSkills: skills.filter((skill) => skill.highlighted).map((skill) => skill.name),
    // Compétences exigées par l'offre mais absentes du profil : signalées, JAMAIS
    // ajoutées au CV (respect de la fidélité / anti-invention).
    missingSkills: offerSkills.filter((skill) => !owned.has(skill)),
  };
}

// Nombre de compétences de l'offre mentionnées dans une expérience (mesure de
// pertinence). L'expérience peut être une chaîne ou un objet : on l'aplatit en
// texte sans en altérer le contenu.
function experienceRelevance(experience, offerSkills) {
  const text = typeof experience === "string" ? experience : JSON.stringify(experience ?? "");
  const wanted = new Set(offerSkills);
  return findSkillsInText(text).filter((skill) => wanted.has(skill)).length;
}

// Réordonne les expériences par pertinence décroissante (tri stable), contenu
// inchangé — on renvoie les mêmes éléments, dans un autre ordre.
function tailorExperiences(experiences, offerSkills) {
  return (experiences ?? [])
    .map((experience, order) => ({ experience, order, relevance: experienceRelevance(experience, offerSkills) }))
    .sort((a, b) => b.relevance - a.relevance || a.order - b.order)
    .map((entry) => entry.experience);
}

// Réordonne les langues pour placer d'abord celles attendues par l'offre.
function tailorLanguages(languages, offerLanguages) {
  const wanted = new Set(offerLanguages);
  return (languages ?? [])
    .map((language, order) => ({
      language,
      order,
      priority: wanted.has(String(language).toLowerCase()) ? 0 : 1,
    }))
    .sort((a, b) => a.priority - b.priority || a.order - b.order)
    .map((entry) => entry.language);
}

// Produit un CV adapté à une offre à partir du profil, par sélection et
// réordonnancement fidèles. `options.resumeId` permet de tracer le CV de
// référence. Le résultat ne contient que des éléments issus du profil ; les
// compétences manquantes sont listées à part (missingSkills), jamais intégrées.
function adaptResumeToOffer(profile = {}, offerKeyInfo = {}, options = {}) {
  const offerSkills = offerKeyInfo.skills ?? [];
  const { skills, highlightedSkills, missingSkills } = tailorSkills(profile, offerSkills);

  return {
    profileId: profile.id ?? null,
    name: profile.name ?? "",
    contractType: profile.contractType ?? null,
    skills,
    highlightedSkills,
    missingSkills,
    experiences: tailorExperiences(profile.experiences, offerSkills),
    languages: tailorLanguages(profile.languages, offerKeyInfo.languages ?? []),
    sourceResumeId: options.resumeId ?? null,
  };
}

module.exports = {
  adaptResumeToOffer,
  collectProfileSkills,
  tailorSkills,
  tailorExperiences,
  tailorLanguages,
};
