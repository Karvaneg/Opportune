// Lexique partagé des compétences reconnues par Opportune : source unique de
// vérité du vocabulaire « compétences ». Utilisé pour extraire les compétences
// d'une offre (offerKeyInfoExtractor) ET pour canoniser celles d'un profil,
// afin que les deux côtés parlent le même vocabulaire lors de la comparaison
// offre↔profil (offerProfileComparator).
const { containsTerm } = require("./textMatch");

// Compétences reconnues : nom canonique + variantes rencontrées dans les offres.
// L'ordre définit l'ordre d'apparition dans les résultats ; il est structuré par
// familles (langages, front, back, données, cloud, devops, outils, méthodo).
const SKILL_CATALOG = [
  // Langages
  { name: "JavaScript", aliases: ["javascript"] },
  { name: "TypeScript", aliases: ["typescript"] },
  { name: "Python", aliases: ["python"] },
  { name: "Java", aliases: ["java"] },
  { name: "C#", aliases: ["c#", ".net", "dotnet"] },
  { name: "C++", aliases: ["c++"] },
  { name: "Go", aliases: ["golang"] },
  { name: "PHP", aliases: ["php"] },
  { name: "Ruby", aliases: ["ruby", "rails"] },
  // Runtime / back JS
  { name: "Node.js", aliases: ["node.js", "nodejs"] },
  // Frameworks front
  { name: "React", aliases: ["react", "react.js", "reactjs"] },
  { name: "Vue.js", aliases: ["vue.js", "vuejs", "vue"] },
  { name: "Angular", aliases: ["angular"] },
  { name: "Next.js", aliases: ["next.js", "nextjs"] },
  { name: "Svelte", aliases: ["svelte", "sveltekit"] },
  { name: "Astro", aliases: ["astro"] },
  // Frameworks back
  { name: "Express", aliases: ["express.js", "expressjs"] },
  { name: "NestJS", aliases: ["nestjs", "nest.js"] },
  { name: "Symfony", aliases: ["symfony"] },
  { name: "Laravel", aliases: ["laravel"] },
  { name: "Django", aliases: ["django"] },
  { name: "Flask", aliases: ["flask"] },
  { name: "FastAPI", aliases: ["fastapi"] },
  { name: "Spring", aliases: ["spring boot", "spring"] },
  // Bases de données
  { name: "SQL", aliases: ["sql", "postgresql", "postgres", "mysql"] },
  { name: "MongoDB", aliases: ["mongodb", "mongo"] },
  { name: "Redis", aliases: ["redis"] },
  { name: "Elasticsearch", aliases: ["elasticsearch"] },
  // Bases de données managées / BaaS
  { name: "Supabase", aliases: ["supabase"] },
  { name: "Firebase", aliases: ["firebase"] },
  { name: "Neon", aliases: ["neon"] },
  { name: "PlanetScale", aliases: ["planetscale"] },
  // Cloud & hébergement
  { name: "AWS", aliases: ["aws"] },
  { name: "GCP", aliases: ["gcp", "google cloud"] },
  { name: "Azure", aliases: ["azure"] },
  { name: "Vercel", aliases: ["vercel"] },
  { name: "Netlify", aliases: ["netlify"] },
  // Casse exacte requise : « render » est aussi un terme technique courant.
  { name: "Render", aliases: ["Render"], caseSensitive: true },
  { name: "Cloudflare", aliases: ["cloudflare"] },
  { name: "Heroku", aliases: ["heroku"] },
  // DevOps / CI-CD
  { name: "Docker", aliases: ["docker"] },
  { name: "Kubernetes", aliases: ["kubernetes", "k8s"] },
  { name: "Terraform", aliases: ["terraform"] },
  { name: "Ansible", aliases: ["ansible"] },
  { name: "DevOps", aliases: ["devops"] },
  { name: "CI/CD", aliases: ["ci/cd", "cicd"] },
  { name: "GitHub Actions", aliases: ["github actions"] },
  { name: "GitLab CI", aliases: ["gitlab ci"] },
  { name: "Jenkins", aliases: ["jenkins"] },
  // Outils
  { name: "Git", aliases: ["git"] },
  { name: "GraphQL", aliases: ["graphql"] },
  // Casse exacte requise : « notion » est aussi un mot courant (« des notions
  // de… ») et le nom d'un niveau de compétence — seule la majuscule distingue.
  { name: "Notion", aliases: ["Notion"], caseSensitive: true },
  { name: "Jira", aliases: ["jira"] },
  { name: "Figma", aliases: ["figma"] },
  // Méthodologie
  { name: "Agile", aliases: ["agile"] },
  { name: "Scrum", aliases: ["scrum"] },
  { name: "Kanban", aliases: ["kanban"] },
];

// Liste des noms canoniques (ordre du catalogue).
const SKILL_NAMES = SKILL_CATALOG.map((skill) => skill.name);

// Noms canoniques des compétences présentes dans un texte, dans l'ordre du
// catalogue et sans doublon. Base de l'extraction côté offre.
function findSkillsInText(text) {
  if (typeof text !== "string" || text.trim() === "") return [];
  const found = [];
  for (const { name, aliases, caseSensitive } of SKILL_CATALOG) {
    if (aliases.some((alias) => containsTerm(text, alias, caseSensitive))) found.push(name);
  }
  return found;
}

// Nom canonique correspondant à un libellé de compétence (saisie libre d'un
// profil, ex. « PostgreSQL » → « SQL »), ou null si non reconnu. Base de la
// canonisation côté profil, pour comparer offre et profil sur le même vocabulaire.
function canonicalizeSkillName(label) {
  if (typeof label !== "string" || label.trim() === "") return null;
  for (const { name, aliases, caseSensitive } of SKILL_CATALOG) {
    if (aliases.some((alias) => containsTerm(label, alias, caseSensitive))) return name;
  }
  return null;
}

module.exports = { SKILL_CATALOG, SKILL_NAMES, findSkillsInText, canonicalizeSkillName };
