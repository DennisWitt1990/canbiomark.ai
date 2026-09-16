import React from "react";
import { useNavigate } from "react-router-dom";

export type ButtonVariant = "primary" | "secondary" | "tertiary" | "danger";

interface ButtonProps {
    children?: React.ReactNode;
    onClick?: () => void;
    /** Navigate here when clicked; can be combined with `onClick`. */
    route?: string;
    className?: string;
    disabled?: boolean;
    variant?: ButtonVariant;
    type?: "button" | "submit";
    title?: string;
}

/** The single button style of the application. */
const Button: React.FC<ButtonProps> = ({
    children,
    onClick,
    route,
    className = "",
    variant = "primary",
    disabled = false,
    type = "button",
    title,
}) => {
    const navigate = useNavigate();

    const handleClick = () => {
        if (route) {
            navigate(route);
        }
        onClick?.();
    };

    const variantClassName = ((): string => {
        switch (variant) {
            case "primary":
                return "bg-black text-white border-black rounded-full";
            case "secondary":
                return "bg-white text-black border-black rounded-md";
            case "tertiary":
                return "bg-white text-black border-black rounded-full";
            case "danger":
                return "bg-white text-red-700 border-red-600 rounded-md hover:bg-red-50";
        }
    })();

    return (
        <button
            type={type}
            title={title}
            disabled={disabled}
            onClick={handleClick}
            className={`font-normal enabled:cursor-pointer flex items-center justify-start border-2 p-4 shadow-md overflow-hidden text-left transition disabled:opacity-40 disabled:cursor-not-allowed ${variantClassName} ${className}`}
        >
            {children}
        </button>
    );
};

export default Button;
