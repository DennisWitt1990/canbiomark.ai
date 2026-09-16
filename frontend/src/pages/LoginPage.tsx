import React, { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api/ApiError";
import Button from "../components/Button";
import StatusMessage from "../components/StatusMessage";
import TextField from "../components/TextField";
import { useAuthentication } from "../context/AuthenticationContext";

/** Username and password sign-in; replaces the former invite-code screen. */
const LoginPage: React.FC = () => {
    const navigate = useNavigate();
    const location = useLocation();
    const { logIn } = useAuthentication();

    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);

    const intendedPath =
        (location.state as { intendedPath?: string } | null)?.intendedPath ?? "/home";

    const canSubmit = username.trim().length > 0 && password.length > 0 && !isSubmitting;

    const handleSubmit = async (event: React.FormEvent) => {
        event.preventDefault();
        if (!canSubmit) {
            return;
        }

        setIsSubmitting(true);
        setErrorMessage(null);
        try {
            const user = await logIn(username.trim(), password);
            // A freshly created or reset account has to pick its own password.
            navigate(user.mustChangePassword ? "/account" : intendedPath, { replace: true });
        } catch (cause) {
            setErrorMessage(ApiError.from(cause, "Sign-in failed.").message);
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="w-full min-h-screen flex items-center justify-center bg-gray-100 p-6">
            <form
                onSubmit={handleSubmit}
                className="w-full max-w-md bg-white rounded-xl shadow p-6 flex flex-col gap-5"
            >
                <div className="flex flex-col items-center gap-3">
                    <img src="/Logo.webp" alt="CanBiomark.ai logo" className="h-24 w-24 object-contain" />
                    <h1 className="text-xl font-bold text-black">Sign in to CanBiomark.ai</h1>
                    <p className="text-sm text-gray-600 text-center">
                        Accounts are created by an administrator. Contact them if you need access.
                    </p>
                </div>

                <TextField
                    label="Username"
                    value={username}
                    onChange={setUsername}
                    autoComplete="username"
                    disabled={isSubmitting}
                    autoFocus
                />

                <TextField
                    label="Password"
                    type="password"
                    value={password}
                    onChange={setPassword}
                    autoComplete="current-password"
                    disabled={isSubmitting}
                />

                {errorMessage && <StatusMessage tone="error">{errorMessage}</StatusMessage>}

                <Button
                    type="submit"
                    variant="primary"
                    className="h-11 justify-center"
                    disabled={!canSubmit}
                >
                    {isSubmitting ? "Signing in ..." : "Sign in"}
                </Button>
            </form>
        </div>
    );
};

export default LoginPage;
