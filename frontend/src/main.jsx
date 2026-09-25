import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// served with the app, so it works offline and users' browsers never call Google
import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";
import App from "./App.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
