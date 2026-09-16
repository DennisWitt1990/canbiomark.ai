import React from "react";
import { useNavigate } from "react-router-dom";

/** The first screen; clicking the logo enters the application. */
const SplashPage: React.FC = () => {
    const navigate = useNavigate();

    return (
        <div className="w-full h-screen flex items-center justify-center bg-white">
            <button
                type="button"
                onClick={() => navigate("/home")}
                aria-label="Open CanBiomark.ai"
                className="cursor-pointer"
            >
                <img src="/Logo.webp" alt="CanBiomark.ai logo" className="h-80 w-80 object-contain" />
            </button>
        </div>
    );
};

export default SplashPage;
