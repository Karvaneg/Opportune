// Modification des documents avant validation (OPP-052). Permet à l'humain de
// corriger le CV adapté et la lettre avant l'envoi, en RE-VÉRIFIANT à chaque
// édition l'absence d'invention (inventionGuard) : une correction ne doit pas
// réintroduire un outil ou un élément absent du profil.
//
// L'édition n'est jamais bloquée ici ; le résultat porte une `verification` que
// le sas d'envoi (OPP-053) exploitera pour autoriser — ou non — l'envoi.
const { verifyText, verifyAdaptedResume } = require("./inventionGuard");

// Ne conserve que les champs autorisés d'un objet de modifications (évite de
// changer par accident l'id, le type ou d'autres métadonnées).
function pick(source, keys) {
  const out = {};
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(source, key)) out[key] = source[key];
  }
  return out;
}

// Applique des corrections à une lettre (subject / body / highlightedSkills) puis
// re-vérifie le corps édité (verifyText) : capte tout outil introduit à la main
// et absent du profil. Retourne { document, verification }.
function editCoverLetter(letter = {}, changes = {}, profile = {}) {
  const document = { ...letter, ...pick(changes, ["subject", "body", "highlightedSkills"]) };
  const verification = verifyText(document.body ?? "", profile);
  return { document, verification };
}

// Applique des corrections à un CV adapté (skills / experiences / highlightedSkills
// / languages) puis re-vérifie sa fidélité (verifyAdaptedResume) : compétences et
// expériences doivent rester issues du profil. Retourne { document, verification }.
function editAdaptedResume(resume = {}, changes = {}, profile = {}) {
  const document = {
    ...resume,
    ...pick(changes, ["skills", "experiences", "highlightedSkills", "languages"]),
  };
  const verification = verifyAdaptedResume(document, profile);
  return { document, verification };
}

module.exports = { editCoverLetter, editAdaptedResume };
