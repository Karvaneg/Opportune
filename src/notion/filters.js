// Filtres exposés par getTickets : nom d'argument -> propriété Notion + type.
// Ajouter un filtre = une seule ligne ici.
const FILTERS = {
  statut: { property: "Statut", type: "status" },
  priorite: { property: "Priorité", type: "select" },
  phase: { property: "Phase", type: "select" },
};

// Construit le filtre Notion à partir des arguments non nuls.
// Les clés inconnues sont ignorées silencieusement.
function buildFilter(filtres = {}) {
  const conditions = Object.entries(filtres)
    .filter(([cle, valeur]) => valeur != null && FILTERS[cle])
    .map(([cle, valeur]) => {
      const { property, type } = FILTERS[cle];
      return { property, [type]: { equals: valeur } };
    });
  return conditions.length ? { and: conditions } : undefined;
}

module.exports = { FILTERS, buildFilter };
