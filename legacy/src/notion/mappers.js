// Lecteurs de propriétés Notion (Notion -> valeur simple).
const read = {
  text: (prop) => (prop?.title || prop?.rich_text || []).map((t) => t.plain_text).join(""),
  select: (prop) => prop?.select?.name ?? null,
  status: (prop) => prop?.status?.name ?? null,
};

// Écrivains de propriétés Notion (valeur simple -> format Notion).
const write = {
  select: (name) => ({ select: { name } }),
  status: (name) => ({ status: { name } }),
};

// Schéma unique : champ du ticket -> [nom de la propriété Notion, lecteur].
// Ajouter un champ = une seule ligne ici.
const SCHEMA = {
  id: ["ID", read.text],
  titre: ["Titre", read.text],
  statut: ["Statut", read.status],
  priorite: ["Priorité", read.select],
  type: ["Type", read.select],
  phase: ["Phase", read.select],
  epic: ["Epic", read.select],
  estimation: ["Estimation", read.select],
};

// Transforme une page Notion brute en ticket normalisé.
function toTicket(page) {
  const ticket = { url: page.url, pageId: page.id };
  for (const [champ, [nomProp, lecteur]] of Object.entries(SCHEMA)) {
    ticket[champ] = lecteur(page.properties[nomProp]);
  }
  return ticket;
}

module.exports = { read, write, SCHEMA, toTicket };
