import React, {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useState,
} from "react";
import { apiRegistry } from "../api/ApiRegistry";
import { ApiError } from "../api/ApiError";
import type { CurrentUser } from "../api/AuthenticationApi";

/** Where the authentication check currently stands. */
export type AuthenticationStatus = "checking" | "signed-in" | "signed-out";

interface AuthenticationContextValue {
    status: AuthenticationStatus;
    currentUser: CurrentUser | null;
    logIn: (username: string, password: string) => Promise<CurrentUser>;
    logOut: () => Promise<void>;
    refresh: () => Promise<void>;
}

const AuthenticationContext = createContext<AuthenticationContextValue | null>(null);

/**
 * Holds the signed-in account for the whole application.
 *
 * The session itself lives in an HttpOnly cookie that JavaScript cannot read,
 * so the only way to learn who is signed in is to ask the backend.
 */
export const AuthenticationProvider: React.FC<{ children: React.ReactNode }> = ({
    children,
}) => {
    const [status, setStatus] = useState<AuthenticationStatus>("checking");
    const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);

    const refresh = useCallback(async () => {
        try {
            const user = await apiRegistry.authentication.fetchCurrentUser();
            setCurrentUser(user);
            setStatus("signed-in");
        } catch (cause) {
            const error = ApiError.from(cause);
            if (!error.isUnauthenticated) {
                console.error("Could not verify the session:", error.message);
            }
            setCurrentUser(null);
            setStatus("signed-out");
        }
    }, []);

    useEffect(() => {
        void refresh();
    }, [refresh]);

    const logIn = useCallback(async (username: string, password: string) => {
        const user = await apiRegistry.authentication.logIn(username, password);
        setCurrentUser(user);
        setStatus("signed-in");
        return user;
    }, []);

    const logOut = useCallback(async () => {
        try {
            await apiRegistry.authentication.logOut();
        } finally {
            setCurrentUser(null);
            setStatus("signed-out");
        }
    }, []);

    const contextValue = useMemo<AuthenticationContextValue>(
        () => ({ status, currentUser, logIn, logOut, refresh }),
        [status, currentUser, logIn, logOut, refresh],
    );

    return (
        <AuthenticationContext.Provider value={contextValue}>
            {children}
        </AuthenticationContext.Provider>
    );
};

/** Read the authentication state; throws when used outside the provider. */
export function useAuthentication(): AuthenticationContextValue {
    const contextValue = useContext(AuthenticationContext);
    if (!contextValue) {
        throw new Error("useAuthentication must be used inside an AuthenticationProvider.");
    }
    return contextValue;
}
