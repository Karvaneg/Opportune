import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { SpaceProvider } from "./space/SpaceContext";
import "./index.css";

const root = document.getElementById("root");
if (!root) throw new Error("élément #root introuvable");

// `SpaceProvider` est la porte d'entrée (OPP-182) : il porte le choix d'espace et pose l'en-tête
// `X-Opportune-Space`. L'`AuthProvider` vit **sous** ce choix (dans `App`, keyé par l'espace),
// pour que `GET /me` soit toujours sondé dans le contexte de l'espace sélectionné.
createRoot(root).render(
  <StrictMode>
    <SpaceProvider>
      <App />
    </SpaceProvider>
  </StrictMode>,
);
