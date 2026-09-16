import React, { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuthentication } from "../../context/AuthenticationContext";

/** Top navigation; the admin entry only appears for administrators. */
const Headerbar: React.FC = () => {
    const navigate = useNavigate();
    const { currentUser, logOut } = useAuthentication();
    const [isSigningOut, setIsSigningOut] = useState(false);

    const handleSignOut = async () => {
        setIsSigningOut(true);
        try {
            await logOut();
            navigate("/login", { replace: true });
        } finally {
            setIsSigningOut(false);
        }
    };

    const navigationLinkClassName = ({ isActive }: { isActive: boolean }): string =>
        `text-sm px-3 py-2 rounded-md transition ${
            isActive ? "bg-black text-white" : "text-black hover:bg-gray-100"
        }`;

    return (
        <header className="flex items-center justify-between bg-white text-black px-6 py-3 border-b border-gray-200">
            <div className="flex items-center gap-6">
                <Link to="/home" className="flex items-center">
                    <img src="/Logo.webp" alt="CanBiomark.ai logo" className="h-12 w-12 object-contain" />
                    <span className="ml-1 text-lg font-semibold">CanBiomark.ai</span>
                </Link>

                <nav className="hidden md:flex items-center gap-1">
                    <NavLink to="/cell-selection" className={navigationLinkClassName}>
                        Cell selector
                    </NavLink>
                    <NavLink to="/tissue-generator" className={navigationLinkClassName}>
                        Tissue generator
                    </NavLink>
                    <NavLink to="/ai-suite" className={navigationLinkClassName}>
                        AI suite
                    </NavLink>
                    {currentUser?.isAdministrator && (
                        <>
                            <NavLink to="/admin/datasets" className={navigationLinkClassName}>
                                Datasets
                            </NavLink>
                            <NavLink to="/admin/users" className={navigationLinkClassName}>
                                Users
                            </NavLink>
                        </>
                    )}
                </nav>
            </div>

            <div className="flex items-center gap-3">
                <NavLink to="/help" className={navigationLinkClassName} title="Help">
                    Help
                </NavLink>

                {currentUser && (
                    <div className="flex items-center gap-3 border-l border-gray-200 pl-3">
                        <div className="hidden sm:flex flex-col items-end leading-tight">
                            <span className="text-sm font-medium">{currentUser.displayName}</span>
                            <span className="text-xs text-gray-500">
                                {currentUser.isAdministrator ? "Administrator" : "Researcher"}
                            </span>
                        </div>
                        <Link
                            to="/account"
                            title="Account settings"
                            className="h-9 w-9 rounded-full bg-black text-white text-xs font-semibold flex items-center justify-center"
                        >
                            {currentUser.initials}
                        </Link>
                        <button
                            type="button"
                            onClick={handleSignOut}
                            disabled={isSigningOut}
                            className="text-sm px-3 py-2 rounded-md border border-black hover:bg-gray-100 disabled:opacity-40"
                        >
                            {isSigningOut ? "Signing out ..." : "Sign out"}
                        </button>
                    </div>
                )}
            </div>
        </header>
    );
};

export default Headerbar;
