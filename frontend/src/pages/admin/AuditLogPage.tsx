import React, { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../api/ApiError";
import { apiRegistry } from "../../api/ApiRegistry";
import type { AuditEvent } from "../../api/AdministrationApi";
import Button from "../../components/Button";
import Card from "../../components/Card";
import { Spinner } from "../../components/Spinner";
import StatusMessage from "../../components/StatusMessage";

/** Read-only view of the administrative audit trail. */
const AuditLogPage: React.FC = () => {
    const [events, setEvents] = useState<AuditEvent[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);

    const loadEvents = useCallback(async () => {
        setIsLoading(true);
        setErrorMessage(null);
        try {
            setEvents(await apiRegistry.administration.listAuditEvents(200));
        } catch (cause) {
            setErrorMessage(ApiError.from(cause, "The audit trail could not be loaded.").message);
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        void loadEvents();
    }, [loadEvents]);

    return (
        <div className="flex flex-col gap-6">
            <div className="flex items-start justify-between gap-4">
                <div className="flex flex-col gap-1">
                    <h1 className="text-2xl font-bold text-black">Audit trail</h1>
                    <p className="text-sm text-gray-600">
                        Sign-ins, failed attempts and every administrative change.
                    </p>
                </div>
                <Button
                    variant="secondary"
                    className="h-10 px-4"
                    onClick={loadEvents}
                    disabled={isLoading}
                >
                    Refresh
                </Button>
            </div>

            {errorMessage && <StatusMessage tone="error">{errorMessage}</StatusMessage>}

            <Card>
                {isLoading ? (
                    <div className="flex items-center gap-3 text-sm text-gray-600 py-6">
                        <Spinner className="h-6 w-6" />
                        Loading ...
                    </div>
                ) : events.length === 0 ? (
                    <p className="text-sm text-gray-600 py-4">No events recorded yet.</p>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="text-left text-gray-500 border-b border-gray-200">
                                    <th className="py-2 pr-3 font-medium">When</th>
                                    <th className="py-2 pr-3 font-medium">Actor</th>
                                    <th className="py-2 pr-3 font-medium">Action</th>
                                    <th className="py-2 pr-3 font-medium">Subject</th>
                                    <th className="py-2 font-medium">Detail</th>
                                </tr>
                            </thead>
                            <tbody>
                                {events.map((event) => (
                                    <tr key={event.event_id} className="border-b border-gray-100">
                                        <td className="py-2 pr-3 whitespace-nowrap text-gray-600">
                                            {new Date(event.occurred_at).toLocaleString()}
                                        </td>
                                        <td className="py-2 pr-3 font-mono text-xs">
                                            {event.actor_username ?? "—"}
                                        </td>
                                        <td className="py-2 pr-3">
                                            <span
                                                className={`text-xs px-2 py-1 rounded-full border ${
                                                    event.action.endsWith(".failed")
                                                        ? "bg-red-50 text-red-700 border-red-200"
                                                        : "bg-gray-50 text-gray-700 border-gray-200"
                                                }`}
                                            >
                                                {event.action}
                                            </span>
                                        </td>
                                        <td className="py-2 pr-3 font-mono text-xs">
                                            {event.subject ?? "—"}
                                        </td>
                                        <td className="py-2 text-gray-600">{event.detail || "—"}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Card>
        </div>
    );
};

export default AuditLogPage;
