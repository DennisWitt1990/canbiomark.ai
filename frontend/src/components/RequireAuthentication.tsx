import React from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuthentication } from "../context/AuthenticationContext";
import { Spinner } from "./Spinner";

interface RequireAuthenticationProps {
    /** When true, a signed-in non-administrator is sent back to the home page. */
    administratorOnly?: boolean;
}

/**
 * Route guard.
 *
 * This is convenience only — the backend enforces the same rules on every
 * request, so a user who edits the URL gains nothing.
 */
const RequireAuthentication: React.FC<RequireAuthenticationProps> = ({
    administratorOnly = false,
}) => {
    const { status, currentUser } = useAuthentication();
    const location = useLocation();

    if (status === "checking") {
        return (
            <div className="w-full h-screen flex items-center justify-center bg-white">
                <div className="flex items-center gap-3 text-sm text-gray-600">
                    <Spinner className="h-8 w-8" />
                    Checking your session ...
                </div>
            </div>
        );
    }

    if (status === "signed-out" || !currentUser) {
        return <Navigate to="/login" replace state={{ intendedPath: location.pathname }} />;
    }

    if (administratorOnly && !currentUser.isAdministrator) {
        return <Navigate to="/home" replace />;
    }

    return <Outlet />;
};

export default RequireAuthentication;
