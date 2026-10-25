const { test } = require("node:test");
const assert = require("node:assert/strict");

const { normalizeUrl, groupDuplicates, dedupeOffers } = require("./offerDeduplicator");
const { createOffer } = require("../models/jobOffer");

test("normalizeUrl : retire protocole, www, fragment et slash final", () => {
  assert.equal(normalizeUrl("https://www.Site.com/Job/"), "site.com/job");
  assert.equal(normalizeUrl("http://site.com/job#top"), "site.com/job");
  assert.equal(normalizeUrl(""), "");
});

test("groupDuplicates : regroupe deux offres de même URL (variations mineures)", () => {
  const a = createOffer({ id: "a", url: "https://www.site.com/job/" });
  const b = createOffer({ id: "b", url: "http://site.com/job" });
  const groups = groupDuplicates([a, b]);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].duplicates.length, 1);
});

test("groupDuplicates : regroupe par titre+entreprise+localisation, conserve sources et urls", () => {
  const o1 = createOffer({
    id: "1", title: "Développeur JS", company: "ACME", location: "Paris",
    source: "linkedin", url: "https://linkedin.com/1",
  });
  const o2 = createOffer({
    id: "2", title: "developpeur js", company: "acme", location: "PARIS",
    source: "indeed", url: "https://indeed.com/2",
  });
  const groups = groupDuplicates([o1, o2]);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].primary.id, "1"); // première rencontrée
  assert.deepEqual(groups[0].sources.sort(), ["indeed", "linkedin"]);
  assert.equal(groups[0].urls.length, 2); // les deux URLs conservées
});

test("groupDuplicates : offres distinctes → groupes séparés", () => {
  const a = createOffer({ id: "a", title: "Dev", company: "ACME" });
  const b = createOffer({ id: "b", title: "Data Eng", company: "Globex" });
  assert.equal(groupDuplicates([a, b]).length, 2);
});

test("groupDuplicates : transitivité (A≡B par URL, B≡C par champs)", () => {
  const a = createOffer({ id: "a", url: "https://x.com/1" });
  const b = createOffer({ id: "b", url: "https://x.com/1", title: "Dev", company: "ACME" });
  const c = createOffer({ id: "c", title: "Dev", company: "ACME" });
  const groups = groupDuplicates([a, b, c]);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].duplicates.length, 2);
});

test("groupDuplicates : distinctIds isole un faux positif", () => {
  const a = createOffer({ id: "a", title: "Dev", company: "ACME" });
  const b = createOffer({ id: "b", title: "Dev", company: "ACME" });
  assert.equal(groupDuplicates([a, b]).length, 1); // regroupées par défaut
  assert.equal(groupDuplicates([a, b], { distinctIds: ["b"] }).length, 2); // séparées
});

test("dedupeOffers : renvoie une opportunité principale par groupe", () => {
  const o1 = createOffer({ id: "1", title: "Dev", company: "ACME", source: "linkedin" });
  const o2 = createOffer({ id: "2", title: "dev", company: "acme", source: "indeed" });
  const o3 = createOffer({ id: "3", title: "Data", company: "Globex" });
  const deduped = dedupeOffers([o1, o2, o3]);
  assert.deepEqual(deduped.map((o) => o.id), ["1", "3"]);
});
