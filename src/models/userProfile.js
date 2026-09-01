// Modèle du profil candidat : structure, valeurs par défaut et construction.
// Sert de référence à Opportune pour comparer les offres à la situation
// de l'utilisateur. La validation vit dans src/services/profileService.js ;
// la persistance dans src/models/profileStore.js.

// Types de contrat reconnus (réutilisés par la validation).
const CONTRACT_TYPES = ["CDI", "freelance", "les deux"];

// Champs obligatoires pour qu'un profil soit exploitable par l'analyse d'offres.
// Les autres champs sont facultatifs et reçoivent une valeur par défaut neutre.
const REQUIRED_FIELDS = ["name", "skills", "contractType"];

// Construit un profil complet à partir de données partielles.
// Chaque champ absent reçoit une valeur par défaut (liste vide ou null).
function createProfile(data = {}) {
  return {
    name: data.name ?? "", // obligatoire
    skills: data.skills ?? [], // compétences — obligatoire (au moins une)
    contractType: data.contractType ?? null, // CDI | freelance | les deux — obligatoire
    experiences: data.experiences ?? [], // expériences
    location: data.location ?? null, // localisation
    mobility: data.mobility ?? null, // mobilité
    remote: data.remote ?? null, // télétravail souhaité
    minCompensation: data.minCompensation ?? null, // salaire ou TJM minimum
    languages: data.languages ?? [], // langues
    availability: data.availability ?? null, // disponibilité
    constraints: data.constraints ?? [], // contraintes particulières
  };
}

// Retourne une copie du profil avec les modifications appliquées (immutable).
function updateProfile(profile, changes = {}) {
  return { ...profile, ...changes };
}

module.exports = { CONTRACT_TYPES, REQUIRED_FIELDS, createProfile, updateProfile };
