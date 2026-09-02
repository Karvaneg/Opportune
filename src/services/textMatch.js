// Appariement de termes dans un texte, partagé par les extracteurs et le
// lexique de compétences. Détecte un terme comme unité entière (pas en sous-mot).

// Vrai si `term` apparaît dans `haystack` comme unité entière. Les frontières
// sont des caractères non alphanumériques (Unicode), ce qui gère aussi bien les
// termes classiques que ceux à ponctuation (c++, c#, node.js).
// `caseSensitive` exige la casse exacte du terme : utile pour les noms propres
// qui sont aussi des mots courants (Notion vs « notions de… », Render vs
// « rendering »), où seule la majuscule distingue l'outil du mot.
function containsTerm(haystack, term, caseSensitive = false) {
  const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const flags = caseSensitive ? "u" : "iu";
  const re = new RegExp(`(^|[^\\p{L}\\p{N}])${escaped}([^\\p{L}\\p{N}]|$)`, flags);
  return re.test(haystack);
}

module.exports = { containsTerm };
