// Rappels de relance sur Discord (OPP-063). Critère : les relances à venir sont
// notifiées. Branche le suivi des relances (followUpPlanner, OPP-062) sur le format
// de messages Discord : sélectionne les candidatures dont la relance est due (ou
// arrive dans un horizon donné), construit un message de rappel (embed) et l'envoie
// via un client injecté.
//
// Même parti pris que discordValidationAdapter (OPP-054) : AUCUNE dépendance à
// discord.js et AUCUN accès réseau. La fonction d'envoi (`send`) est fournie par
// l'appelant (bot réel, webhook, log de test…) ; l'adaptateur se contente de parler
// le format Discord et de décider quoi notifier — donc entièrement testable hors ligne.
const { listApplications } = require("./applicationService");
const { isTerminal } = require("./applicationStatus");
const { DEFAULT_PATH } = require("../models/applicationStore");

// Couleur de l'embed de rappel (jaune « attention »).
const REMINDER_COLOR = 0xf1c40f;

// Vrai si la valeur est une date interprétable (chaîne non vide et parseable).
function isValidDateString(value) {
  return typeof value === "string" && value.trim() !== "" && !Number.isNaN(Date.parse(value));
}

// Millisecondes correspondant à `now` (Date ou chaîne) décalé de `days` jours.
function horizonMs(now, days) {
  const base = now instanceof Date ? now.getTime() : Date.parse(now);
  return base + days * 24 * 60 * 60 * 1000;
}

// Candidatures d'un profil à notifier : relance planifiée, candidature non close, et
// date de relance atteinte (échue) ou comprise dans l'horizon (`horizonDays` jours à
// partir de `now`). Triées par date de relance croissante (les plus urgentes d'abord).
function listFollowUpsToNotify(profileId, { now = new Date(), horizonDays = 0, filePath = DEFAULT_PATH } = {}) {
  const limit = horizonMs(now, horizonDays);
  return listApplications(profileId, filePath)
    .filter(
      (app) =>
        isValidDateString(app.followUpAt) &&
        !isTerminal(app.status) &&
        Date.parse(app.followUpAt) <= limit,
    )
    .sort((a, b) => Date.parse(a.followUpAt) - Date.parse(b.followUpAt));
}

// Construit le message Discord de rappel pour un ensemble de candidatures. Un champ
// par relance : intitulé de l'offre (résolu via `resolveOffer` si fourni, sinon
// l'offerId) + date de relance et statut. Suppose applications non vide.
function buildFollowUpReminderMessage(applications, { resolveOffer } = {}) {
  const fields = applications.map((app) => {
    const resolved = typeof resolveOffer === "function" ? resolveOffer(app.offerId) : null;
    const title = resolved?.title ?? app.offerId;
    return { name: String(title), value: `Relance prévue le ${app.followUpAt} — statut : ${app.status}` };
  });

  return {
    embeds: [
      {
        title: `⏰ ${applications.length} relance(s) à effectuer`,
        color: REMINDER_COLOR,
        fields,
      },
    ],
  };
}

// Notifie sur Discord les relances à venir d'un profil. Récupère les candidatures à
// relancer, et n'envoie un message QUE s'il y en a (via la fonction `send` injectée).
//
// Options : send (obligatoire), now, horizonDays (0 = seulement les échues),
// filePath, resolveOffer. Retourne { count, reminded, message } ; message vaut null
// et send n'est pas appelé lorsqu'aucune relance n'est à notifier.
async function remindDueFollowUps(profileId, options = {}) {
  const { send, now = new Date(), horizonDays = 0, filePath = DEFAULT_PATH, resolveOffer } = options;
  if (typeof send !== "function") {
    throw new Error("remindDueFollowUps : la fonction d'envoi (send) est requise");
  }

  const reminded = listFollowUpsToNotify(profileId, { now, horizonDays, filePath });
  if (reminded.length === 0) return { count: 0, reminded: [], message: null };

  const message = buildFollowUpReminderMessage(reminded, { resolveOffer });
  await send(message);
  return { count: reminded.length, reminded, message };
}

module.exports = {
  listFollowUpsToNotify,
  buildFollowUpReminderMessage,
  remindDueFollowUps,
};
