import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/ApiError";
import { apiRegistry } from "../../api/ApiRegistry";
import type { ManagedUser } from "../../api/AdministrationApi";
import Button from "../../components/Button";
import Card from "../../components/Card";
import { Spinner } from "../../components/Spinner";
import StatusMessage from "../../components/StatusMessage";
import { useAuthentication } from "../../context/AuthenticationContext";
import CreateUserForm from "./CreateUserForm";
import UserDetailPanel from "./UserDetailPanel";

const DEFAULT_QUOTA_GIGABYTES = 50;

/** The administrator's overview of every account. */
const UserAdministrationPage: React.FC = () => {
    const { currentUser } = useAuthentication();

    const [users, setUsers] = useState<ManagedUser[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const [searchTerm, setSearchTerm] = useState("");
    const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
    const [isCreateFormOpen, setIsCreateFormOpen] = useState(false);

    const loadUsers = useCallback(async () => {
        setIsLoading(true);
        setErrorMessage(null);
        try {
            setUsers(await apiRegistry.administration.listUsers());
        } catch (cause) {
            setErrorMessage(ApiError.from(cause, "The user list could not be loaded.").message);
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        void loadUsers();
    }, [loadUsers]);

    const filteredUsers = useMemo(() => {
        const normalizedTerm = searchTerm.trim().toLowerCase();
        if (!normalizedTerm) {
            return users;
        }
        return users.filter((user) =>
            `${user.username} ${user.displayName} ${user.role}`
                .toLowerCase()
                .includes(normalizedTerm),
        );
    }, [users, searchTerm]);

    const selectedUser = users.find((user) => user.userId === selectedUserId) ?? null;

    const administratorCount = users.filter(
        (user) => user.isAdministrator && user.isActive,
    ).length;

    const handleUserChanged = (updatedUser: ManagedUser) => {
        // Refresh the whole list: quota and session counts may have shifted too.
        void loadUsers();
        setSelectedUserId(updatedUser.userId);
    };

    const handleUserDeleted = (deletedUserId: string) => {
        setUsers((previousUsers) =>
            previousUsers.filter((user) => user.userId !== deletedUserId),
        );
        setSelectedUserId(null);
    };

    return (
        <div className="flex flex-col gap-6">
            <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="flex flex-col gap-1">
                    <h1 className="text-2xl font-bold text-black">User administration</h1>
                    <p className="text-sm text-gray-600">
                        Create accounts, set quotas and roles, reset passwords and revoke access.
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant="secondary"
                        className="h-10 px-4"
                        onClick={loadUsers}
                        disabled={isLoading}
                    >
                        Refresh
                    </Button>
                    <Button
                        variant="primary"
                        className="h-10 px-4"
                        onClick={() => setIsCreateFormOpen((isOpen) => !isOpen)}
                    >
                        {isCreateFormOpen ? "Hide the form" : "New account"}
                    </Button>
                </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <SummaryTile label="Accounts" value={String(users.length)} />
                <SummaryTile label="Administrators" value={String(administratorCount)} />
                <SummaryTile
                    label="Disabled"
                    value={String(users.filter((user) => !user.isActive).length)}
                />
                <SummaryTile
                    label="Signed in"
                    value={String(
                        users.filter((user) => user.activeSessionCount > 0).length,
                    )}
                />
            </div>

            {errorMessage && <StatusMessage tone="error">{errorMessage}</StatusMessage>}

            {isCreateFormOpen && (
                <CreateUserForm
                    defaultQuotaGigabytes={DEFAULT_QUOTA_GIGABYTES}
                    onUserCreated={() => void loadUsers()}
                />
            )}

            <Card
                title="Accounts"
                actions={
                    <input
                        type="search"
                        value={searchTerm}
                        placeholder="Search by name or role ..."
                        onChange={(event) => setSearchTerm(event.target.value)}
                        className="border border-gray-300 rounded px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black"
                    />
                }
            >
                {isLoading ? (
                    <div className="flex items-center gap-3 text-sm text-gray-600 py-6">
                        <Spinner className="h-6 w-6" />
                        Loading the accounts ...
                    </div>
                ) : filteredUsers.length === 0 ? (
                    <p className="text-sm text-gray-600 py-4">No account matches the search.</p>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="text-left text-gray-500 border-b border-gray-200">
                                    <th className="py-2 pr-3 font-medium">User</th>
                                    <th className="py-2 pr-3 font-medium">Role</th>
                                    <th className="py-2 pr-3 font-medium">Status</th>
                                    <th className="py-2 pr-3 font-medium">Storage</th>
                                    <th className="py-2 pr-3 font-medium">Sessions</th>
                                    <th className="py-2 pr-3 font-medium">Last sign-in</th>
                                    <th className="py-2 font-medium" />
                                </tr>
                            </thead>
                            <tbody>
                                {filteredUsers.map((user) => (
                                    <tr
                                        key={user.userId}
                                        className={`border-b border-gray-100 ${
                                            user.userId === selectedUserId ? "bg-gray-50" : ""
                                        }`}
                                    >
                                        <td className="py-2 pr-3">
                                            <div className="flex flex-col">
                                                <span className="font-medium">{user.displayName}</span>
                                                <span className="font-mono text-xs text-gray-500">
                                                    {user.username}
                                                </span>
                                            </div>
                                        </td>
                                        <td className="py-2 pr-3">
                                            <RoleBadge isAdministrator={user.isAdministrator} />
                                        </td>
                                        <td className="py-2 pr-3">
                                            <StatusBadge user={user} />
                                        </td>
                                        <td className="py-2 pr-3 whitespace-nowrap">
                                            <div className="flex flex-col gap-1">
                                                <span>
                                                    {user.usedDiskLabel} / {user.quotaGigabytes} GB
                                                </span>
                                                <QuotaBar percent={user.quotaUsedPercent} />
                                            </div>
                                        </td>
                                        <td className="py-2 pr-3">{user.activeSessionCount}</td>
                                        <td className="py-2 pr-3 whitespace-nowrap text-gray-600">
                                            {user.lastLoginAt?.toLocaleDateString() ?? "never"}
                                        </td>
                                        <td className="py-2">
                                            <button
                                                type="button"
                                                onClick={() =>
                                                    setSelectedUserId(
                                                        user.userId === selectedUserId
                                                            ? null
                                                            : user.userId,
                                                    )
                                                }
                                                className="text-sm underline hover:no-underline"
                                            >
                                                {user.userId === selectedUserId ? "Close" : "Manage"}
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Card>

            {selectedUser && currentUser && (
                <UserDetailPanel
                    user={selectedUser}
                    signedInUserId={currentUser.userId}
                    onUserChanged={handleUserChanged}
                    onUserDeleted={handleUserDeleted}
                    onClose={() => setSelectedUserId(null)}
                />
            )}
        </div>
    );
};

const SummaryTile: React.FC<{ label: string; value: string }> = ({ label, value }) => (
    <div className="bg-white rounded-xl shadow p-4 flex flex-col gap-1">
        <span className="text-xs uppercase tracking-wide text-gray-500">{label}</span>
        <span className="text-2xl font-semibold text-black">{value}</span>
    </div>
);

const RoleBadge: React.FC<{ isAdministrator: boolean }> = ({ isAdministrator }) => (
    <span
        className={`text-xs px-2 py-1 rounded-full border ${
            isAdministrator
                ? "bg-black text-white border-black"
                : "bg-white text-gray-700 border-gray-300"
        }`}
    >
        {isAdministrator ? "Administrator" : "Researcher"}
    </span>
);

const StatusBadge: React.FC<{ user: ManagedUser }> = ({ user }) => {
    const toneClassName = !user.isActive
        ? "bg-red-50 text-red-700 border-red-200"
        : user.mustChangePassword
          ? "bg-amber-50 text-amber-800 border-amber-200"
          : "bg-emerald-50 text-emerald-700 border-emerald-200";

    return (
        <span className={`text-xs px-2 py-1 rounded-full border ${toneClassName}`}>
            {user.statusLabel}
        </span>
    );
};

const QuotaBar: React.FC<{ percent: number }> = ({ percent }) => {
    const clampedPercent = Math.max(0, Math.min(100, percent));
    const barColorClassName =
        clampedPercent >= 90 ? "bg-red-600" : clampedPercent >= 70 ? "bg-amber-500" : "bg-black";

    return (
        <div className="h-1.5 w-28 bg-gray-200 rounded" title={`${percent}% of the quota used`}>
            <div
                className={`h-1.5 rounded ${barColorClassName}`}
                style={{ width: `${clampedPercent}%` }}
            />
        </div>
    );
};

export default UserAdministrationPage;
