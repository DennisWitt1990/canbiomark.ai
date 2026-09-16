import React from "react";

/** The single loading indicator of the application. */
export const Spinner: React.FC<{ className?: string }> = ({ className = "h-10 w-10" }) => (
    <div
        role="status"
        aria-label="Loading"
        className={`animate-spin rounded-full border-4 border-gray-700 border-t-transparent ${className}`}
    />
);

export default Spinner;
