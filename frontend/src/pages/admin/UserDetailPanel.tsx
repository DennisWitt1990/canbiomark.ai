import React, { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../api/ApiError";
import { apiRegistry } from "../../api/ApiRegistry";
import type { ManagedUser, UserSession } from "../../api/AdministrationApi";
import { UserRole, type UserRoleName } from "../../api/AuthenticationApi";
import Button from "../../components/Button";
import Card from "../../components/Card";
import ConfirmDialog from "../../components/ConfirmDialog";
import CopyableSecret from "../../components/CopyableSecret";
import StatusMessage from "../../components/StatusMessage";
import TextField from "../../components/TextField";

interface UserDetailPanelProps {
    user: ManagedUser;
    /** The administrator viewing this panel; guards self-destructive actions. */
    signedInUserId: string;
    onUserChanged: (user: ManagedUser) => void;
    onUserDeleted: (userId: string) => void;
    onClose: () => void;
}

type PendingAction = "delete" | "revoke-sessions" | null;

/** Edit one account: profile, role, quota, password, sessions and deletion. */
const UserDetailPanel: React.FC<UserDetailPanelProps> = ({
    user,
    signedInUserId,
    onUserChanged,
    onUserDeleted,
    onClose,
}) => {
    const [displayName, setDisplayName] = useState(user.displayName);
    const [role, setRole] = useState<UserRoleName>(user.role);
    const [quotaGigabytes, setQuotaGigabytes] = useState(String(user.quotaGigabytes));
    const [isActive, setIsActive] = useState(user.isActive);

    const [sessions, setSessions] = useState<UserSession[]>([]);
    const [newPassword, setNewPassword] = useState("");
    const [shouldGeneratePassword, setShouldGeneratePassword] = useState(true);
    const [resetPasswordResult, setResetPasswordResult] = useState<string | null>(null);

    const [isBusy, setIsBusy] = useState(false);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);
    const [pendingAction, setPendingAction] = useState<PendingAction>(null);

    const isOwnAccount = user.userId === signedInUserId;

    useEffect(() => {
        setDisplayName(user.displayName);
        setRole(user.role);
        setQuotaGigabytes(String(user.quotaGigabytes));
        setIsActive(user.isActive);
        setResetPasswordResult(null);
        setSuccessMessage(null);
        setErrorMessage(null);
    }, [user]);

    const loadSessions = useCallback(async () => {
        try {
            setSessions(await apiRegistry.administration.listSessions(user.userId));
        } catch (cause) {
            setErrorMessage(ApiError.from(cause, "Could not load the sessions.").message);
        }
    }, [user.userId]);

    useEffect(() => {
        void loadSessions();
    }, [loadSessions]);

    const runGuarded = async (action: () => Promise<void>, failureMessage: string) => {
        setIsBusy(true);
        setErrorMessage(null);
        setSuccessMessage(null);
        try {
            await action();
        } catch (cause) {
            setErrorMessage(ApiError.from(cause, failureMessage).message);
        } finally {
            setIsBusy(false);
        }
    };

    const handleSaveProfile = () =>
        runGuarded(async () => {
            const parsedQuota = Number.parseInt(quotaGigabytes, 10);
            const updatedUser = await apiRegistry.administration.updateUser(user.userId, {
                displayName: displayName.trim(),
                role,
                quotaGigabytes: Number.isFinite(parsedQuota) ? parsedQuota : undefined,
                isActive,
            });
            onUserChanged(updatedUser);
            setSuccessMessage("The changes were saved.");
        }, "The changes could not be saved.");

    const handleResetPassword = () =>
        runGuarded(async () => {
            const issuedPassword = await apiRegistry.administration.resetPassword(
                user.userId,
                shouldGeneratePassword ? null : newPassword,
                true,
            );
            setResetPasswordResult(issuedPassword);
            setNewPassword("");
            // A reset signs the user out everywhere.
            await loadSessions();
        }, "The password could not be reset.");

    const handleRevokeSessions = () =>
        runGuarded(async () => {
            const revokedCount = await apiRegistry.administration.revokeSessions(user.userId);
            setSuccessMessage(`${revokedCount} session(s) were terminated.`);
            setPendingAction(null);
            await loadSessions();
        }, "The sessions could not be terminated.");

    const handleDelete = () =>
        runGuarded(async () => {
            await apiRegistry.administration.deleteUser(user.userId, true);
            setPendingAction(null);
            onUserDeleted(user.userId);
        }, "The account could not be deleted.");

    return (
        <Card
            title={`Manage "${user.username}"`}
            description={`Created ${user.createdAt.toLocaleDateString()} · ${user.usedDiskLabel} used`}
            actions={
                <Button variant="secondary" className="h-9 px-3" onClick={onClose}>
                    Close
                </Button>
            }
        >
            {errorMessage && <StatusMessage tone="error">{errorMessage}</StatusMessage>}
            {successMessage && <StatusMessage tone="success">{successMessage}</StatusMessage>}
            {isOwnAccount && (
                <StatusMessage tone="info">
                    This is your own account. You cannot delete it, and the server refuses any
                    change that would leave the installation without an administrator.
                </StatusMessage>
            )}

            {/* --- profile --- */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <TextField
                    label="Display name"
                    value={displayName}
                    onChange={setDisplayName}
                    disabled={isBusy}
                />

                <label className="flex flex-col gap-1">
                    <span className="text-sm font-medium text-black">Role</span>
                    <select
                        value={role}
                        disabled={isBusy}
                        onChange={(event) => setRole(event.target.value as UserRoleName)}
                        className="border border-gray-300 rounded px-3 py-2 outline-none focus:ring-2 focus:ring-black"
                    >
                        <option value={UserRole.Researcher}>Researcher</option>
                        <option value={UserRole.Administrator}>Administrator</option>
                    </select>
                </label>

                <TextField
                    label="Storage quota (GB)"
                    type="number"
                    min={0}
                    value={quotaGigabytes}
                    onChange={setQuotaGigabytes}
                    disabled={isBusy}
                    hint={`Currently using ${user.usedDiskLabel} (${user.quotaUsedPercent}%).`}
                />

                <label className="flex items-center gap-2 text-sm self-end pb-2">
                    <input
                        type="checkbox"
                        checked={isActive}
                        disabled={isBusy}
                        onChange={(event) => setIsActive(event.target.checked)}
                    />
                    Account is active (disabling signs the user out immediately)
                </label>
            </div>

            <Button
                variant="primary"
                className="h-10 px-4 justify-center w-fit"
                onClick={handleSaveProfile}
                disabled={isBusy}
            >
                Save changes
            </Button>

            {/* --- password --- */}
            <div className="border-t border-gray-200 pt-4 flex flex-col gap-3">
                <h3 className="text-sm font-semibold">Reset the password</h3>
                <p className="text-xs text-gray-600">
                    The new password is shown once. Resetting also signs the user out everywhere
                    and asks them to choose their own password at the next sign-in.
                </p>

                <label className="flex items-center gap-2 text-sm">
                    <input
                        type="radio"
                        checked={shouldGeneratePassword}
                        onChange={() => setShouldGeneratePassword(true)}
                        disabled={isBusy}
                    />
                    Generate a strong password
                </label>
                <label className="flex items-center gap-2 text-sm">
                    <input
                        type="radio"
                        checked={!shouldGeneratePassword}
                        onChange={() => setShouldGeneratePassword(false)}
                        disabled={isBusy}
                    />
                    Set it myself
                </label>

                {!shouldGeneratePassword && (
                    <TextField
                        label="New password"
                        type="password"
                        value={newPassword}
                        onChange={setNewPassword}
                        autoComplete="new-password"
                        disabled={isBusy}
                    />
                )}

                <Button
                    variant="secondary"
                    className="h-10 px-4 justify-center w-fit"
                    onClick={handleResetPassword}
                    disabled={isBusy || (!shouldGeneratePassword && newPassword.length === 0)}
                >
                    Reset password
                </Button>

                {resetPasswordResult && (
                    <CopyableSecret
                        label={`New password for "${user.username}"`}
                        secret={resetPasswordResult}
                    />
                )}
            </div>

            {/* --- sessions --- */}
            <div className="border-t border-gray-200 pt-4 flex flex-col gap-3">
                <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold">
                        Active sessions ({sessions.length})
                    </h3>
                    <Button
                        variant="secondary"
                        className="h-9 px-3"
                        onClick={() => setPendingAction("revoke-sessions")}
                        disabled={isBusy || sessions.length === 0}
                    >
                        Sign out everywhere
                    </Button>
                </div>

                {sessions.length === 0 ? (
                    <p className="text-sm text-gray-600">No active session.</p>
                ) : (
                    <ul className="flex flex-col gap-2">
                        {sessions.map((session) => (
                            <li
                                key={session.session_id_preview}
                                className="text-xs border border-gray-200 rounded p-2 flex flex-col gap-1"
                            >
                                <span className="font-mono">{session.session_id_preview}…</span>
                                <span className="text-gray-600">
                                    Signed in {new Date(session.created_at).toLocaleString()} · expires{" "}
                                    {new Date(session.expires_at).toLocaleString()}
                                </span>
                                <span className="text-gray-500 break-all">
                                    {session.client_description || "unknown client"}
                                </span>
                            </li>
                        ))}
                    </ul>
                )}
            </div>

            {/* --- deletion --- */}
            <div className="border-t border-gray-200 pt-4 flex flex-col gap-2">
                <h3 className="text-sm font-semibold text-red-800">Delete the account</h3>
                <p className="text-xs text-gray-600">
                    Deletes the account together with every file in its workspace. This cannot be
                    undone.
                </p>
                <Button
                    variant="danger"
                    className="h-10 px-4 justify-center w-fit"
                    onClick={() => setPendingAction("delete")}
                    disabled={isBusy || isOwnAccount}
                    title={isOwnAccount ? "You cannot delete your own account." : undefined}
                >
                    Delete account
                </Button>
            </div>

            {pendingAction === "delete" && (
                <ConfirmDialog
                    title="Delete this account?"
                    isDestructive
                    busy={isBusy}
                    confirmLabel="Delete permanently"
                    message={
                        <>
                            The account <strong>{user.username}</strong> and its entire workspace
                            ({user.usedDiskLabel}) will be removed permanently. This cannot be
                            undone.
                        </>
                    }
                    onConfirm={handleDelete}
                    onCancel={() => setPendingAction(null)}
                />
            )}

            {pendingAction === "revoke-sessions" && (
                <ConfirmDialog
                    title="Sign this user out everywhere?"
                    busy={isBusy}
                    confirmLabel="Sign out everywhere"
                    message={
                        <>
                            All {sessions.length} session(s) of <strong>{user.username}</strong>{" "}
                            end immediately. The password stays unchanged.
                        </>
                    }
                    onConfirm={handleRevokeSessions}
                    onCancel={() => setPendingAction(null)}
                />
            )}
        </Card>
    );
};

export default UserDetailPanel;
