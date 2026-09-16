/// <reference types="vite/client" />

interface ImportMetaEnv {
    /** Base URL of the backend; empty when it is served from the same origin. */
    readonly VITE_API_URL?: string;
}

interface ImportMeta {
    readonly env: ImportMetaEnv;
}

/** Injected by Vite from package.json at build time. */
declare const __APP_VERSION__: string;
