import React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { apiRegistry } from "../../api/ApiRegistry";
import Button from "../../components/Button";
import Card from "../../components/Card";

/** Step 3 of the cell selector: download the result or continue to SimBu. */
const CellSelectionDonePage: React.FC = () => {
    const navigate = useNavigate();
    const location = useLocation();
    const finalPath = (location.state as { finalPath?: string } | null)?.finalPath;

    if (!finalPath) {
        return (
            <Card title="No result">
                <p className="text-sm text-gray-600">
                    There is no finished dataset to show. Please run the cell selector again.
                </p>
                <Button
                    variant="primary"
                    className="h-10 px-4 w-fit justify-center"
                    route="/cell-selection"
                >
                    Back to the cell selector
                </Button>
            </Card>
        );
    }

    return (
        <div className="flex justify-center py-6">
            <Card title="The dataset is ready" className="max-w-2xl">
                <p className="text-sm text-gray-600">Saved in your workspace as:</p>
                <code className="bg-gray-100 px-3 py-2 rounded text-sm break-all">
                    {finalPath}
                </code>

                <div className="flex flex-col sm:flex-row gap-3 pt-2">
                    <a
                        href={apiRegistry.workspace.buildDownloadUrl(finalPath)}
                        className="px-4 py-2 rounded-md border-2 border-black bg-white text-black text-sm text-center hover:bg-gray-50"
                    >
                        Download the file
                    </a>
                    <Button
                        variant="primary"
                        className="h-10 px-4 justify-center"
                        onClick={() => navigate("/tissue-generator", { state: { finalPath } })}
                    >
                        Continue to the tissue generator
                    </Button>
                </div>

                <p className="text-sm text-gray-600 pt-2">
                    The tissue generator can simulate synthetic bulk RNA-seq data from this
                    dataset. Results stay in your workspace until you delete them.
                </p>
            </Card>
        </div>
    );
};

export default CellSelectionDonePage;
