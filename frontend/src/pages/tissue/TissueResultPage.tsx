import React from "react";
import { useLocation } from "react-router-dom";
import { apiRegistry } from "../../api/ApiRegistry";
import { SimulationResult, type SimulationResultPayload } from "../../api/TissueGeneratorApi";
import Button from "../../components/Button";
import Card from "../../components/Card";
import StatusMessage from "../../components/StatusMessage";

interface ResultLocationState {
    result: SimulationResult | SimulationResultPayload;
    parameters: {
        immuneCellFraction: number;
        sampleCount: number;
        sampleBaseName: string;
    };
}

/** Shows the artifacts and logs of a finished single run. */
const TissueResultPage: React.FC = () => {
    const location = useLocation();
    const state = location.state as ResultLocationState | null;

    if (!state?.result) {
        return (
            <Card title="No result">
                <p className="text-sm text-gray-600">
                    The result is only held for this page view and was lost on reload. Please run
                    the simulation again.
                </p>
                <Button
                    variant="primary"
                    className="h-10 px-4 w-fit justify-center"
                    route="/tissue-generator"
                >
                    Back to the tissue generator
                </Button>
            </Card>
        );
    }

    // React Router serialises the state, so rebuild the class to keep its helpers.
    const result =
        state.result instanceof SimulationResult
            ? state.result
            : new SimulationResult(state.result as SimulationResultPayload);
    const { parameters } = state;

    return (
        <div className="flex flex-col gap-6">
            <div className="flex items-start justify-between gap-4">
                <div className="flex flex-col gap-1">
                    <h1 className="text-2xl font-bold text-black">Simulation result</h1>
                    <p className="text-sm text-gray-600">
                        Artifacts and logs of your SimBu run.
                    </p>
                </div>
                <Button variant="secondary" className="h-10 px-4" route="/tissue-generator">
                    Back
                </Button>
            </div>

            <StatusMessage tone={result.succeeded ? "success" : "error"}>
                {result.succeeded
                    ? `The simulation finished successfully (input: ${result.inputSourceLabel}).`
                    : `The simulation failed with return code ${result.returnCode}. See the logs below.`}
            </StatusMessage>

            <Card title="Parameters">
                <dl className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
                    <div>
                        <dt className="text-gray-500">Sample name</dt>
                        <dd className="font-mono">{parameters.sampleBaseName}</dd>
                    </div>
                    <div>
                        <dt className="text-gray-500">Immune cell fraction</dt>
                        <dd className="font-mono">{parameters.immuneCellFraction}</dd>
                    </div>
                    <div>
                        <dt className="text-gray-500">Samples</dt>
                        <dd className="font-mono">{parameters.sampleCount}</dd>
                    </div>
                </dl>
            </Card>

            {result.hasDownloadableArtifacts && (
                <Card title="Generated files">
                    <ul className="flex flex-col gap-2 text-sm">
                        {result.plotPath && (
                            <ArtifactRow label="Plot (PDF)" relativePath={result.plotPath} />
                        )}
                        {result.countsPath && (
                            <ArtifactRow label="Counts (TXT)" relativePath={result.countsPath} />
                        )}
                    </ul>
                </Card>
            )}

            <Card title="Logs">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <LogPanel title="Standard output" content={result.standardOutput} />
                    <LogPanel title="Standard error" content={result.standardError} />
                </div>

                {result.succeeded && (
                    <div className="border-t border-gray-200 pt-4 flex flex-col gap-2">
                        <p className="text-sm text-gray-700">
                            You can now benchmark the generated tissues in the AI suite. Download
                            the files first if you want to keep them locally.
                        </p>
                        <Button
                            variant="primary"
                            className="h-10 px-4 w-fit justify-center"
                            route="/ai-suite"
                        >
                            Continue to the AI suite
                        </Button>
                    </div>
                )}
            </Card>
        </div>
    );
};

const ArtifactRow: React.FC<{ label: string; relativePath: string }> = ({
    label,
    relativePath,
}) => (
    <li className="flex items-center justify-between gap-3 border border-gray-200 rounded px-3 py-2">
        <div className="flex flex-col">
            <span className="font-medium">{label}</span>
            <span className="font-mono text-xs text-gray-500 break-all">{relativePath}</span>
        </div>
        <a
            href={apiRegistry.workspace.buildDownloadUrl(relativePath)}
            className="text-sm underline hover:no-underline whitespace-nowrap"
        >
            Download
        </a>
    </li>
);

const LogPanel: React.FC<{ title: string; content: string }> = ({ title, content }) => (
    <div className="flex flex-col gap-1">
        <span className="text-xs font-semibold">{title}</span>
        <pre className="text-xs bg-gray-50 border border-gray-200 rounded p-2 overflow-auto max-h-96 whitespace-pre-wrap">
            {content || "—"}
        </pre>
    </div>
);

export default TissueResultPage;
