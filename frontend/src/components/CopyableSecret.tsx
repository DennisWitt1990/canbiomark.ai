import React, { useState } from "react";
import Button from "./Button";

interface CopyableSecretProps {
    label: string;
    secret: string;
    note?: string;
}

/**
 * Shows a password once and lets the administrator copy it.
 *
 * The backend returns a generated or reset password exactly once; it is never
 * retrievable afterwards, so this makes handing it over reliable.
 */
const CopyableSecret: React.FC<CopyableSecretProps> = ({ label, secret, note }) => {
    const [wasCopied, setWasCopied] = useState(false);

    const copyToClipboard = async () => {
        try {
            await navigator.clipboard.writeText(secret);
            setWasCopied(true);
            window.setTimeout(() => setWasCopied(false), 2500);
        } catch {
            // Clipboard access can be blocked; the value stays visible to select.
            setWasCopied(false);
        }
    };

    return (
        <div className="border border-amber-200 bg-amber-50 rounded p-3 flex flex-col gap-2">
            <div className="text-sm font-semibold text-amber-900">{label}</div>
            <div className="flex items-center gap-3 flex-wrap">
                <code className="font-mono text-sm bg-white border border-amber-200 rounded px-3 py-2 select-all break-all">
                    {secret}
                </code>
                <Button variant="secondary" className="h-9 px-3" onClick={copyToClipboard}>
                    {wasCopied ? "Copied" : "Copy"}
                </Button>
            </div>
            <p className="text-xs text-amber-900">
                {note ??
                    "Write this down now and pass it on securely. It cannot be shown again."}
            </p>
        </div>
    );
};

export default CopyableSecret;
