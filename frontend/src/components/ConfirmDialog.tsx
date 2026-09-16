import React from "react";
import Button from "./Button";

interface ConfirmDialogProps {
    title: string;
    message: React.ReactNode;
    confirmLabel?: string;
    cancelLabel?: string;
    isDestructive?: boolean;
    busy?: boolean;
    onConfirm: () => void;
    onCancel: () => void;
}

/** A modal confirmation used before anything irreversible. */
const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
    title,
    message,
    confirmLabel = "Confirm",
    cancelLabel = "Cancel",
    isDestructive = false,
    busy = false,
    onConfirm,
    onCancel,
}) => (
    <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
        onClick={onCancel}
    >
        <div
            className="w-full max-w-lg bg-white rounded-xl shadow-xl p-5 flex flex-col gap-4"
            onClick={(event) => event.stopPropagation()}
        >
            <h2 className="text-lg font-semibold text-black">{title}</h2>
            <div className="text-sm text-gray-700">{message}</div>
            <div className="flex items-center justify-end gap-3">
                <Button variant="secondary" className="h-10 px-4" onClick={onCancel} disabled={busy}>
                    {cancelLabel}
                </Button>
                <Button
                    variant={isDestructive ? "danger" : "primary"}
                    className="h-10 px-4"
                    onClick={onConfirm}
                    disabled={busy}
                >
                    {busy ? "Working ..." : confirmLabel}
                </Button>
            </div>
        </div>
    </div>
);

export default ConfirmDialog;
