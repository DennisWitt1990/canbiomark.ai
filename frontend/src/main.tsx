import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthenticationProvider } from "./context/AuthenticationContext";
import "./index.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
    throw new Error("The element #root is missing from index.html.");
}

createRoot(rootElement).render(
    <React.StrictMode>
        <BrowserRouter>
            <AuthenticationProvider>
                <App />
            </AuthenticationProvider>
        </BrowserRouter>
    </React.StrictMode>,
);
