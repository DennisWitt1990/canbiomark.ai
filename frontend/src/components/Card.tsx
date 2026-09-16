import React from "react";

interface CardProps {
    title?: string;
    description?: string;
    actions?: React.ReactNode;
    children: React.ReactNode;
    className?: string;
}

/** A white panel with an optional heading; the base layout block of every page. */
const Card: React.FC<CardProps> = ({
    title,
    description,
    actions,
    children,
    className = "",
}) => (
    <section className={`bg-white rounded-xl shadow p-5 flex flex-col gap-4 ${className}`}>
        {(title || actions) && (
            <header className="flex items-start justify-between gap-4">
                <div className="flex flex-col gap-1">
                    {title && <h2 className="text-lg font-semibold text-black">{title}</h2>}
                    {description && <p className="text-sm text-gray-600">{description}</p>}
                </div>
                {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
            </header>
        )}
        {children}
    </section>
);

export default Card;
