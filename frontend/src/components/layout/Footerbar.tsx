import React from "react";

/** Footer with the build version injected by Vite. */
const Footerbar: React.FC = () => (
    <footer className="w-full text-sm text-gray-600 py-3 px-8 bg-white border-t border-gray-200 text-right">
        <p>CanBiomark.ai v{__APP_VERSION__} – All rights reserved © 2026</p>
    </footer>
);

export default Footerbar;
