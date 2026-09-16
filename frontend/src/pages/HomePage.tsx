import React from "react";
import { Link } from "react-router-dom";
import { useAuthentication } from "../context/AuthenticationContext";

interface ModuleTile {
    title: string;
    description: string;
    route: string;
    administratorOnly?: boolean;
}

const MODULE_TILES: ModuleTile[] = [
    {
        title: "Cell selector",
        description:
            "Pick two experiments from the catalogue, merge them and keep only the cell types you need.",
        route: "/cell-selection",
    },
    {
        title: "Synthetic tissue generator",
        description:
            "Simulate bulk RNA-seq tissues with SimBu — a single run, or a whole batch from a CSV file.",
        route: "/tissue-generator",
    },
    {
        title: "AI suite",
        description:
            "Classify by threshold or regress the infiltration fraction directly, with H2O.",
        route: "/ai-suite",
    },
    {
        title: "Import datasets",
        description:
            "Find single-cell datasets on CELLxGENE or EBI and publish them to the shared catalogue.",
        route: "/admin/datasets",
        administratorOnly: true,
    },
    {
        title: "User administration",
        description: "Create accounts, set quotas and roles, reset passwords and revoke access.",
        route: "/admin/users",
        administratorOnly: true,
    },
];

/** Landing page after signing in. */
const HomePage: React.FC = () => {
    const { currentUser } = useAuthentication();

    const visibleTiles = MODULE_TILES.filter(
        (tile) => !tile.administratorOnly || currentUser?.isAdministrator,
    );

    return (
        <div className="flex flex-col items-center gap-8 py-6">
            <div className="flex flex-col items-center gap-2 text-center">
                <h1 className="text-2xl font-bold text-black">
                    Welcome back, {currentUser?.displayName ?? "researcher"}.
                </h1>
                <p className="text-base text-gray-700">Choose a module to get started.</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full max-w-4xl">
                {visibleTiles.map((tile) => (
                    <Link
                        key={tile.route}
                        to={tile.route}
                        className="bg-white rounded-xl shadow p-5 flex flex-col gap-2 border-2 border-transparent hover:border-black transition"
                    >
                        <h2 className="text-lg font-semibold text-black">{tile.title}</h2>
                        <p className="text-sm text-gray-600">{tile.description}</p>
                    </Link>
                ))}
            </div>
        </div>
    );
};

export default HomePage;
