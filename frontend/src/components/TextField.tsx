import React from "react";

interface TextFieldProps {
    label: string;
    value: string;
    onChange: (value: string) => void;
    type?: "text" | "password" | "number";
    placeholder?: string;
    hint?: string;
    disabled?: boolean;
    autoComplete?: string;
    min?: number;
    max?: number;
    autoFocus?: boolean;
}

/** A labelled input; used by every form so they look and behave alike. */
const TextField: React.FC<TextFieldProps> = ({
    label,
    value,
    onChange,
    type = "text",
    placeholder,
    hint,
    disabled = false,
    autoComplete,
    min,
    max,
    autoFocus = false,
}) => (
    <label className="flex flex-col gap-1">
        <span className="text-sm font-medium text-black">{label}</span>
        <input
            type={type}
            value={value}
            placeholder={placeholder}
            disabled={disabled}
            autoComplete={autoComplete}
            autoFocus={autoFocus}
            min={min}
            max={max}
            onChange={(event) => onChange(event.target.value)}
            className="border border-gray-300 rounded px-3 py-2 outline-none focus:ring-2 focus:ring-black disabled:bg-gray-100"
        />
        {hint && <span className="text-xs text-gray-500">{hint}</span>}
    </label>
);

export default TextField;
