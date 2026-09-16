import React from "react";

export type StatusTone = "error" | "success" | "info" | "warning";

interface StatusMessageProps {
    tone: StatusTone;
    children: React.ReactNode;
    className?: string;
}

const TONE_CLASS_NAMES: Record<StatusTone, string> = {
    error: "bg-red-50 border-red-200 text-red-800",
    success: "bg-emerald-50 border-emerald-200 text-emerald-800",
    info: "bg-blue-50 border-blue-200 text-blue-800",
    warning: "bg-amber-50 border-amber-200 text-amber-900",
};

/** An inline banner for errors, confirmations and hints. */
const StatusMessage: React.FC<StatusMessageProps> = ({ tone, children, className = "" }) => (
    <div
        role={tone === "error" ? "alert" : "status"}
        className={`text-sm border rounded p-3 whitespace-pre-wrap ${TONE_CLASS_NAMES[tone]} ${className}`}
    >
        {children}
    </div>
);

export default StatusMessage;
