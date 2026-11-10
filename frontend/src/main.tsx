import React from "react";
import ReactDOM from "react-dom/client";
import Translator from "./pages/Translator";
import Admin from "./pages/Admin";
import "./styles.css";
import { I18nProvider } from "./i18n";
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <I18nProvider>
      {location.pathname.startsWith("/admin") ? <Admin /> : <Translator />}
    </I18nProvider>
  </React.StrictMode>,
);
