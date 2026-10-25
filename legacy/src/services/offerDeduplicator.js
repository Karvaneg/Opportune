// Détection des offres en double / équivalentes provenant de plusieurs sources.
// Approche déterministe (normalisation + égalité, sans fuzzy) : deux offres sont
// équivalentes si elles partagent une URL normalisée OU un triplet
// (titre + entreprise + localisation) normalisé. La transitivité est gérée par
// union-find (A≡B par URL, B≡C par champs ⇒ A,B,C regroupées).

// Normalise un texte : sans accents, minuscules, espaces réduits.
function normalizeText(value) {
  if (typeof value !== "string") return "";
  return value
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "") // retire les diacritiques
    .toLowerCase()
    .trim()
    .replace(/\s+/g, " ");
}

// Normalise une URL : minuscules, sans protocole/www, sans fragment ni slash final.
function normalizeUrl(value) {
  if (typeof value !== "string") return "";
  const u = value.trim().toLowerCase();
  if (u === "") return "";
  return u
    .replace(/^https?:\/\//, "")
    .replace(/^www\./, "")
    .replace(/#.*$/, "")
    .replace(/\/+$/, "");
}

// Signatures d'équivalence d'une offre. Une offre marquée « distincte » (faux
// positif corrigé) ou trop incomplète reçoit une signature unique (son id).
function signaturesFor(offer, distinctIds) {
  if (distinctIds.has(offer.id)) return [`id:${offer.id}`];

  const signatures = [];
  const url = normalizeUrl(offer.url);
  if (url) signatures.push(`url:${url}`);

  const title = normalizeText(offer.title);
  const company = normalizeText(offer.company);
  if (title && company) {
    signatures.push(`fld:${title}|${company}|${normalizeText(offer.location)}`);
  }

  if (signatures.length === 0) signatures.push(`id:${offer.id}`);
  return signatures;
}

// Union-find minimal sur les indices des offres.
function makeDSU(size) {
  const parent = Array.from({ length: size }, (_, i) => i);
  const find = (x) => {
    while (parent[x] !== x) {
      parent[x] = parent[parent[x]];
      x = parent[x];
    }
    return x;
  };
  return {
    find,
    union: (a, b) => {
      parent[find(a)] = find(b);
    },
  };
}

const unique = (values) => [...new Set(values.filter((v) => v !== null && v !== undefined && v !== ""))];

// Construit un groupe { primary, duplicates, sources, urls } à partir d'offres
// équivalentes (la première rencontrée devient l'opportunité principale).
function toGroup(offers) {
  const [primary, ...duplicates] = offers;
  return {
    primary,
    duplicates,
    sources: unique(offers.map((o) => o.source)),
    urls: unique(offers.map((o) => o.url)),
  };
}

// Regroupe les offres équivalentes. options.distinctIds : ids d'offres à traiter
// comme uniques (correction manuelle d'un faux positif). Retourne un tableau de
// groupes, dans l'ordre d'apparition des opportunités principales.
function groupDuplicates(offers = [], options = {}) {
  const distinctIds = new Set(options.distinctIds ?? []);
  const dsu = makeDSU(offers.length);
  const sigToIndex = new Map();

  offers.forEach((offer, i) => {
    for (const sig of signaturesFor(offer, distinctIds)) {
      if (sigToIndex.has(sig)) dsu.union(i, sigToIndex.get(sig));
      else sigToIndex.set(sig, i);
    }
  });

  const groups = new Map();
  offers.forEach((offer, i) => {
    const root = dsu.find(i);
    if (!groups.has(root)) groups.set(root, []);
    groups.get(root).push(offer);
  });

  return [...groups.values()].map(toGroup);
}

// Retourne la liste dédupliquée (une seule opportunité principale par groupe).
function dedupeOffers(offers = [], options = {}) {
  return groupDuplicates(offers, options).map((group) => group.primary);
}

module.exports = {
  normalizeUrl,
  groupDuplicates,
  dedupeOffers,
};
