import React from "react";
import { Outlet } from "react-router-dom";
import Footerbar from "./Footerbar";
import Headerbar from "./Headerbar";

/** Frame around every signed-in page: header, scrollable content, footer. */
const AppLayout: React.FC = () => (
    <div className="fixed inset-0 flex flex-col bg-gray-100 font-sans">
        <Headerbar />
        <main className="flex-1 overflow-y-auto px-6 py-6">
            <div className="mx-auto w-full max-w-6xl">
                <Outlet />
            </div>
        </main>
        <Footerbar />
    </div>
);

export default AppLayout;
