import React from "react";
import { createRoot } from "react-dom/client";
import "./styles/tokens.css";
import { App } from "./App";

const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("Root container #root not found in document");
}

createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
