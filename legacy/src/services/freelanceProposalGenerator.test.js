const { test } = require("node:test");
const assert = require("node:assert/strict");

const { generateFreelanceProposal } = require("./freelanceProposalGenerator");

// Profil freelance de référence.
function freelanceProfile(overrides = {}) {
  return {
    name: "Alex Martin",
    contractType: "freelance",
    skills: ["Python", "SQL"],
    targetDailyRate: 550,
    availability: "immédiate",
    ...overrides,
  };
}

// Mission freelance de référence (client + intitulé + détails).
function mission(overrides = {}) {
  return {
    company: "DataCorp",
    title: "Data Engineer",
    description: "Mission Python, SQL, Java et Airflow.",
    freelance: { duration: "6 mois" },
    ...overrides,
  };
}

test("generateFreelanceProposal : mentionne précisément la mission et le client", () => {
  const proposal = generateFreelanceProposal(freelanceProfile(), mission());
  assert.match(proposal.subject, /Data Engineer — DataCorp/);
  assert.match(proposal.body, /mission de Data Engineer au sein de DataCorp/);
});

test("generateFreelanceProposal : met en avant les compétences réelles, sans en inventer", () => {
  const proposal = generateFreelanceProposal(freelanceProfile(), mission());
  assert.ok(proposal.highlightedSkills.includes("Python"));
  assert.ok(proposal.highlightedSkills.includes("SQL"));
  assert.match(proposal.body, /Python/);
  // Java est exigé par la mission mais absent du profil → jamais dans la proposition.
  assert.doesNotMatch(proposal.body, /Java/);
});

test("generateFreelanceProposal : propose les conditions (TJM, dispo, durée)", () => {
  const proposal = generateFreelanceProposal(freelanceProfile(), mission());
  assert.deepEqual(proposal.terms, { dailyRate: 550, availability: "immédiate", duration: "6 mois" });
  assert.match(proposal.body, /tarif journalier de 550 € \(TJM\)/);
  assert.match(proposal.body, /disponibilité immédiate/);
  assert.match(proposal.body, /durée de 6 mois/);
});

test("generateFreelanceProposal : durée lue depuis raw si le champ freelance est absent", () => {
  const offer = mission({ freelance: undefined, raw: { duree: "3 mois" } });
  const proposal = generateFreelanceProposal(freelanceProfile(), offer);
  assert.equal(proposal.terms.duration, "3 mois");
});

test("generateFreelanceProposal : aucune condition connue → pas de phrase de conditions", () => {
  const profile = freelanceProfile({ targetDailyRate: null, availability: null });
  const offer = mission({ freelance: {} });
  const proposal = generateFreelanceProposal(profile, offer);
  assert.deepEqual(proposal.terms, { dailyRate: null, availability: null, duration: null });
  assert.doesNotMatch(proposal.body, /Je vous propose/);
});

test("generateFreelanceProposal : signe avec le nom du profil quand il est présent", () => {
  const proposal = generateFreelanceProposal(freelanceProfile(), mission());
  assert.ok(proposal.body.trimEnd().endsWith("Alex Martin"));
});

test("generateFreelanceProposal : client ou intitulé manquant → erreur explicite", () => {
  assert.throws(() => generateFreelanceProposal(freelanceProfile(), mission({ company: "" })), /client|mission/i);
  assert.throws(() => generateFreelanceProposal(freelanceProfile(), mission({ title: "  " })), /client|mission/i);
});
