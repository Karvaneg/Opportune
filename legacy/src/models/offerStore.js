// Persistance des offres sur disque, sous forme de collection JSON (tableau).
const fs = require("node:fs");
const path = require("node:path");

// Emplacement par défaut de la collection (dossier data/ ignoré par git).
const DEFAULT_PATH = path.join("data", "offers.json");

// Recharge toutes les offres ; retourne [] si le fichier n'existe pas.
function loadOffers(filePath = DEFAULT_PATH) {
  if (!fs.existsSync(filePath)) return [];
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

// Sauvegarde une offre : la remplace si son id existe déjà, sinon l'ajoute.
// Retourne l'offre enregistrée.
function saveOffer(offer, filePath = DEFAULT_PATH) {
  const offers = loadOffers(filePath);
  const index = offers.findIndex((o) => o.id === offer.id);

  if (index >= 0) offers[index] = offer;
  else offers.push(offer);

  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(offers, null, 2));
  return offer;
}

module.exports = { DEFAULT_PATH, loadOffers, saveOffer };
