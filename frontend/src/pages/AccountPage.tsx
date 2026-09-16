import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/ApiError";
import { apiRegistry } from "../api/ApiRegistry";
import type { PasswordPolicy } from "../api/AuthenticationApi";
import Button from "../components/Button";
import Card from "../components/Card";
import StatusMessage from "../components/StatusMessage";
import TextField from "../components/TextField";
import { useAuthentication } from "../context/AuthenticationContext";

/** The signed-in user's own profile and password change. */
const AccountPage: React.FC = () => {
    const navigate = useNavigate();
    const { currentUser } = useAuthentication();

    const [currentPassword, setCurrentPassword] = useState("");
    const [newPassword, setNewPassword] = useState("");
    const [repeatedPassword, setRepeatedPassword] = useState("");
    const [passwordPolicy, setPasswordPolicy] = useState<PasswordPolicy | null>(null);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);

    useEffect(() => {
        apiRegistry.authentication
            .fetchPasswordPolicy()
            .then(setPasswordPolicy)
            .catch(() => setPasswordPolicy(null));
    }, []);

    const passwordsMatch = newPassword === repeatedPassword;
    const canSubmit =
        currentPassword.length > 0 &&
        newPassword.length > 0 &&
        passwordsMatch &&
        !isSubmitting;

    const handleChangePassword = async (event: React.FormEvent) => {
        event.preventDefault();
        if (!canSubmit) {
            return;
        }

        setIsSubmitting(true);
        setErrorMessage(null);
        setSuccessMessage(null);
        try {
            const message = await apiRegistry.authentication.changeOwnPassword(
                currentPassword,
                newPassword,
            );
            setSuccessMessage(message);
            // Changing the password revokes every session, so sign in again.
            window.setTimeout(() => navigate("/login", { replace: true }), 1800);
        } catch (cause) {
            setErrorMessage(ApiError.from(cause, "The password could not be changed.").message);
        } finally {
            setIsSubmitting(false);
        }
    };

    if (!currentUser) {
        return null;
    }

    return (
        <div className="flex flex-col gap-6">
            <h1 className="text-2xl font-bold text-black">Your account</h1>

            {currentUser.mustChangePassword && (
                <StatusMessage tone="warning">
                    Your password was set by an administrator. Please choose your own password now.
                </StatusMessage>
            )}

            <Card title="Profile">
                <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                    <div>
                        <dt className="text-gray-500">Username</dt>
                        <dd className="font-mono">{currentUser.username}</dd>
                    </div>
                    <div>
                        <dt className="text-gray-500">Display name</dt>
                        <dd>{currentUser.displayName}</dd>
                    </div>
                    <div>
                        <dt className="text-gray-500">Role</dt>
                        <dd>{currentUser.isAdministrator ? "Administrator" : "Researcher"}</dd>
                    </div>
                    <div>
                        <dt className="text-gray-500">Storage quota</dt>
                        <dd>{currentUser.quotaGigabytes} GB</dd>
                    </div>
                    <div>
                        <dt className="text-gray-500">Last sign-in</dt>
                        <dd>{currentUser.lastLoginAt?.toLocaleString() ?? "—"}</dd>
                    </div>
                </dl>
            </Card>

            <Card
                title="Change your password"
                description={passwordPolicy?.description ?? "Choose a strong password."}
                className="max-w-xl"
            >
                <form onSubmit={handleChangePassword} className="flex flex-col gap-4">
                    <TextField
                        label="Current password"
                        type="password"
                        value={currentPassword}
                        onChange={setCurrentPassword}
                        autoComplete="current-password"
                        disabled={isSubmitting}
                    />
                    <TextField
                        label="New password"
                        type="password"
                        value={newPassword}
                        onChange={setNewPassword}
                        autoComplete="new-password"
                        disabled={isSubmitting}
                    />
                    <TextField
                        label="Repeat the new password"
                        type="password"
                        value={repeatedPassword}
                        onChange={setRepeatedPassword}
                        autoComplete="new-password"
                        disabled={isSubmitting}
                        hint={
                            repeatedPassword.length > 0 && !passwordsMatch
                                ? "The two passwords do not match."
                                : undefined
                        }
                    />

                    {errorMessage && <StatusMessage tone="error">{errorMessage}</StatusMessage>}
                    {successMessage && (
                        <StatusMessage tone="success">{successMessage}</StatusMessage>
                    )}

                    <Button
                        type="submit"
                        variant="primary"
                        className="h-10 px-4 justify-center w-fit"
                        disabled={!canSubmit}
                    >
                        {isSubmitting ? "Changing ..." : "Change password"}
                    </Button>
                </form>
            </Card>
        </div>
    );
};

export default AccountPage;
