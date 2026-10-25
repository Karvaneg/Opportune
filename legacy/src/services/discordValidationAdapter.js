// Adaptateur Discord pour la validation humaine (OPP-054). Branche le cœur découplé
// d'opportunityValidation (OPP-050) sur le format de messages/interactions Discord :
// il produit le message de validation RÉEL (embed + boutons) et un gestionnaire
// d'interaction qui déclenche reviewApplication (accepter / rejeter / mettre en
// attente) selon le bouton cliqué.
//
// Cap technique respecté : AUCUNE dépendance à discord.js et AUCUN accès réseau. Le
// client Discord (bot/token) est INJECTÉ par l'appelant ; l'adaptateur se contente
// de parler le format Discord (payload JSON compatible API v10) et de router les
// clics de boutons vers la logique métier pure — donc entièrement testable hors ligne.
const {
  reviewApplication,
  buildValidationMessage,
  VALIDATION_ACTIONS,
  VALIDATION_DECISIONS,
} = require("./opportunityValidation");
const { DEFAULT_PATH } = require("../models/applicationStore");

// Espace de noms des customId de nos boutons : "opp:review:<applicationId>:<decision>".
// Le préfixe permet d'ignorer toute interaction qui n'est pas la nôtre.
const CUSTOM_ID_NAMESPACE = "opp:review";
const CUSTOM_ID_SEPARATOR = ":";

// Types de composants de message Discord (API v10).
const COMPONENT_TYPE = { ACTION_ROW: 1, BUTTON: 2 };

// Styles de bouton Discord (API v10).
const BUTTON_STYLE = { PRIMARY: 1, SECONDARY: 2, SUCCESS: 3, DANGER: 4 };

// Style de bouton par décision : accepter = vert, rejeter = rouge, attente = gris.
const DECISION_STYLE = {
  accept: BUTTON_STYLE.SUCCESS,
  reject: BUTTON_STYLE.DANGER,
  hold: BUTTON_STYLE.SECONDARY,
};

// Couleur de l'embed selon la recommandation (entier RVB, format Discord).
const RECOMMENDATION_COLOR = {
  postuler: 0x2ecc71, // vert
  a_etudier: 0xe67e22, // orange
  ignorer: 0x95a5a6, // gris
};

// --- customId : encodage / décodage ------------------------------------------

// Construit le customId d'un bouton de décision pour une candidature donnée.
function encodeCustomId(applicationId, decision) {
  return [CUSTOM_ID_NAMESPACE, applicationId, decision].join(CUSTOM_ID_SEPARATOR);
}

// Décode un customId de bouton. Retourne { applicationId, decision } si le customId
// est bien l'un des nôtres et porte une décision connue, sinon null.
function parseCustomId(customId) {
  if (typeof customId !== "string") return null;

  const prefix = CUSTOM_ID_NAMESPACE + CUSTOM_ID_SEPARATOR;
  if (!customId.startsWith(prefix)) return null;

  // La décision est le dernier segment ; l'applicationId est tout ce qui reste
  // entre le préfixe et la décision (robuste à un id contenant des séparateurs).
  const rest = customId.slice(prefix.length);
  const lastSep = rest.lastIndexOf(CUSTOM_ID_SEPARATOR);
  if (lastSep <= 0) return null;

  const applicationId = rest.slice(0, lastSep);
  const decision = rest.slice(lastSep + 1);
  if (!VALIDATION_DECISIONS.includes(decision)) return null;

  return { applicationId, decision };
}

// --- Construction du message de validation Discord ---------------------------

// Champ d'embed listant des messages (une puce par ligne). Omis si vide.
function bulletField(name, messages) {
  if (!messages || messages.length === 0) return null;
  return { name, value: messages.map((m) => `• ${m}`).join("\n") };
}

// Construit le message Discord de validation d'une candidature : un embed
// (titre, score, recommandation, raisons) et une rangée de boutons dont les
// customId encodent la décision et l'identifiant de candidature.
function buildDiscordValidationMessage(applicationId, offer = {}, comparison = {}) {
  const message = buildValidationMessage(offer, comparison);

  const fields = [
    { name: "Score", value: `${message.score}/100`, inline: true },
    { name: "Recommandation", value: message.recommendation.label, inline: true },
    bulletField("Points forts", message.positives),
    bulletField("Points d'attention", message.negatives),
  ].filter(Boolean);

  const embed = {
    title: message.title || "Validation d'une candidature",
    color: RECOMMENDATION_COLOR[message.recommendation.action] ?? BUTTON_STYLE.SECONDARY,
    fields,
  };

  const buttons = VALIDATION_ACTIONS.map(({ decision, label }) => ({
    type: COMPONENT_TYPE.BUTTON,
    style: DECISION_STYLE[decision] ?? BUTTON_STYLE.SECONDARY,
    label,
    custom_id: encodeCustomId(applicationId, decision),
  }));

  return {
    embeds: [embed],
    components: [{ type: COMPONENT_TYPE.ACTION_ROW, components: buttons }],
  };
}

// --- Gestion des interactions (clic de bouton) -------------------------------

// Vrai si l'interaction est un clic de bouton (discord.js expose isButton() ;
// un objet simple peut fournir componentType = 2).
function isButtonInteraction(interaction) {
  if (!interaction || typeof interaction.customId !== "string") return false;
  if (typeof interaction.isButton === "function") return interaction.isButton();
  return interaction.componentType === COMPONENT_TYPE.BUTTON;
}

// Libellé lisible d'une décision (pour les messages de confirmation).
function decisionLabel(decision) {
  return VALIDATION_ACTIONS.find((a) => a.decision === decision)?.label ?? decision;
}

// Traite une interaction de bouton Discord : décode le customId, applique la
// décision via reviewApplication, puis met à jour le message d'origine (boutons
// retirés) pour refléter la décision. Répond de façon éphémère en cas d'erreur.
//
// Retourne :
//   - null si l'interaction n'est pas l'un de nos boutons (l'appelant l'ignore) ;
//   - { decision, application, content } en cas de succès ;
//   - { decision, application: null, content, error } si reviewApplication échoue.
// Ne relance jamais : un bot ne doit pas planter sur une décision invalide.
async function handleValidationInteraction(interaction, filePath = DEFAULT_PATH) {
  if (!isButtonInteraction(interaction)) return null;

  const parsed = parseCustomId(interaction.customId);
  if (!parsed) return null;

  const { applicationId, decision } = parsed;

  try {
    const application = reviewApplication(applicationId, decision, filePath);
    const content = `${decisionLabel(decision)} — statut : ${application.status}`;
    if (typeof interaction.update === "function") {
      await interaction.update({ content, embeds: [], components: [] });
    }
    return { decision, application, content };
  } catch (error) {
    const content = `Décision impossible (${decisionLabel(decision)}) : ${error.message}`;
    if (typeof interaction.reply === "function") {
      await interaction.reply({ content, ephemeral: true });
    }
    return { decision, application: null, content, error: error.message };
  }
}

// Fabrique un gestionnaire d'interactions prêt à brancher sur un client Discord
// injecté, p. ex. : client.on("interactionCreate", createValidationInteractionHandler()).
function createValidationInteractionHandler(filePath = DEFAULT_PATH) {
  return (interaction) => handleValidationInteraction(interaction, filePath);
}

module.exports = {
  CUSTOM_ID_NAMESPACE,
  COMPONENT_TYPE,
  BUTTON_STYLE,
  encodeCustomId,
  parseCustomId,
  buildDiscordValidationMessage,
  handleValidationInteraction,
  createValidationInteractionHandler,
};
