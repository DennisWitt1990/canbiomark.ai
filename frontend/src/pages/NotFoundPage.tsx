import React from "react";
import Button from "../components/Button";
import Card from "../components/Card";

/** Shown for any unknown route. */
const NotFoundPage: React.FC = () => (
    <div className="flex justify-center py-10">
        <Card title="Page not found" className="max-w-lg">
            <p className="text-sm text-gray-600">
                The page you asked for does not exist.
            </p>
            <Button variant="primary" className="h-10 px-4 w-fit justify-center" route="/home">
                Back to the start page
            </Button>
        </Card>
    </div>
);

export default NotFoundPage;
