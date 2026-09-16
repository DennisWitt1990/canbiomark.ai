import React, { useState } from "react";
import { ApiError } from "../../api/ApiError";
import { apiRegistry } from "../../api/ApiRegistry";
import type { ManagedUser } from "../../api/AdministrationApi";
import { UserRole, type UserRoleName } from "../../api/AuthenticationApi";
import Button from "../../components/Button";
import Card from "../../components/Card";
import CopyableSecret from "../../components/CopyableSecret";
import StatusMessage from "../../components/StatusMessage";
import TextField from "../../components/TextField";

interface CreateUserFormProps {
    defaultQuotaGigabytes: number;
    onUserCreated: (user: ManagedUser) => void;
}

/** Creates an account and shows its initial password exactly once. */
const CreateUserForm: React.FC<CreateUserFormProps> = ({
    defaultQuotaGigabytes,
    onUserCreated,
}) => {
    const [username, setUsername] = useState("");
    const [displayName, setDisplayName] = useState("");
    const [role, setRole] = useState<UserRoleName>(UserRole.Researcher);
    const [quotaGigabytes, setQuotaGigabytes] = useState(String(defaultQuotaGigabytes));
    const [shouldGeneratePassword, setShouldGeneratePassword] = useState(true);
    const [manualPassword, setManualPassword] = useState("");
    const [requirePasswordChange, setRequirePasswordChange] = useState(true);

    const [isSubmitting, setIsSubmitting] = useState(false);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const [createdCredentials, setCreatedCredentials] = useState<{
        username: string;
        password: string;
    } | null>(null);

    const canSubmit =
        username.trim().length >= 3 &&
        (shouldGeneratePassword || manualPassword.length > 0) &&
        !isSubmitting;

    const resetForm = () => {
        setUsername("");
        setDisplayName("");
        setRole(UserRole.Researcher);
        setQuotaGigabytes(String(defaultQuotaGigabytes));
        setManualPassword("");
        setShouldGeneratePassword(true);
        setRequirePasswordChange(true);
    };

    const handleSubmit = async (event: React.FormEvent) => {
        event.preventDefault();
        if (!canSubmit) {
            return;
        }

        setIsSubmitting(true);
        setErrorMessage(null);
        setCreatedCredentials(null);
        try {
            const parsedQuota = Number.parseInt(quotaGigabytes, 10);
            const { user, initialPassword } = await apiRegistry.administration.createUser({
                username: username.trim(),
                displayName: displayName.trim(),
                role,
                quotaGigabytes: Number.isFinite(parsedQuota) ? parsedQuota : null,
                initialPassword: shouldGeneratePassword ? null : manualPassword,
                requirePasswordChange,
            });

            setCreatedCredentials({ username: user.username, password: initialPassword });
            onUserCreated(user);
            resetForm();
        } catch (cause) {
            setErrorMessage(ApiError.from(cause, "The account could not be created.").message);
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <Card
            title="Create an account"
            description="The new user signs in with the username and the initial password shown here."
        >
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <TextField
                        label="Username"
                        value={username}
                        onChange={setUsername}
                        placeholder="j.doe"
                        hint="At least 3 characters; stored in lower case."
                        disabled={isSubmitting}
                    />
                    <TextField
                        label="Display name"
                        value={displayName}
                        onChange={setDisplayName}
                        placeholder="Jane Doe"
                        disabled={isSubmitting}
                    />

                    <label className="flex flex-col gap-1">
                        <span className="text-sm font-medium text-black">Role</span>
                        <select
                            value={role}
                            disabled={isSubmitting}
                            onChange={(event) => setRole(event.target.value as UserRoleName)}
                            className="border border-gray-300 rounded px-3 py-2 outline-none focus:ring-2 focus:ring-black"
                        >
                            <option value={UserRole.Researcher}>Researcher</option>
                            <option value={UserRole.Administrator}>Administrator</option>
                        </select>
                        <span className="text-xs text-gray-500">
                            Administrators can manage all accounts.
                        </span>
                    </label>

                    <TextField
                        label="Storage quota (GB)"
                        type="number"
                        min={0}
                        value={quotaGigabytes}
                        onChange={setQuotaGigabytes}
                        disabled={isSubmitting}
                    />
                </div>

                <fieldset className="border border-gray-200 rounded p-3 flex flex-col gap-3">
                    <legend className="text-sm font-medium px-1">Initial password</legend>

                    <label className="flex items-center gap-2 text-sm">
                        <input
                            type="radio"
                            checked={shouldGeneratePassword}
                            onChange={() => setShouldGeneratePassword(true)}
                            disabled={isSubmitting}
                        />
                        Generate a strong password automatically (recommended)
                    </label>

                    <label className="flex items-center gap-2 text-sm">
                        <input
                            type="radio"
                            checked={!shouldGeneratePassword}
                            onChange={() => setShouldGeneratePassword(false)}
                            disabled={isSubmitting}
                        />
                        Set the password myself
                    </label>

                    {!shouldGeneratePassword && (
                        <TextField
                            label="Password"
                            type="password"
                            value={manualPassword}
                            onChange={setManualPassword}
                            autoComplete="new-password"
                            disabled={isSubmitting}
                        />
                    )}

                    <label className="flex items-center gap-2 text-sm">
                        <input
                            type="checkbox"
                            checked={requirePasswordChange}
                            onChange={(event) => setRequirePasswordChange(event.target.checked)}
                            disabled={isSubmitting}
                        />
                        Ask the user to choose their own password at first sign-in
                    </label>
                </fieldset>

                {errorMessage && <StatusMessage tone="error">{errorMessage}</StatusMessage>}

                {createdCredentials && (
                    <CopyableSecret
                        label={`Initial password for "${createdCredentials.username}"`}
                        secret={createdCredentials.password}
                    />
                )}

                <Button
                    type="submit"
                    variant="primary"
                    className="h-10 px-4 justify-center w-fit"
                    disabled={!canSubmit}
                >
                    {isSubmitting ? "Creating ..." : "Create account"}
                </Button>
            </form>
        </Card>
    );
};

export default CreateUserForm;
