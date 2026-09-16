import React, { useCallback, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../../api/ApiError";
import { apiRegistry } from "../../api/ApiRegistry";
import Button from "../../components/Button";
import Card from "../../components/Card";
import StatusMessage from "../../components/StatusMessage";
import TextField from "../../components/TextField";

const DATASET_EXTENSION = ".h5ad";

/** Derive the sample base name from a workspace path or a chosen file. */
function deriveSampleBaseName(sourceName: string): string {
    const fileName = sourceName.split("/").pop() ?? "";
    return fileName.replace(/\.h5ad$/i, "").trim();
}

/** Single SimBu run: pick the input, set the parameters, start the simulation. */
const TissueGeneratorPage: React.FC = () => {
    const navigate = useNavigate();
    const location = useLocation();

    const incomingFinalPath = (location.state as { finalPath?: string } | null)?.finalPath;

    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [uploadedSampleName, setUploadedSampleName] = useState<string | null>(null);
    const [uploadProgressPercent, setUploadProgressPercent] = useState(0);
    const [isUploading, setIsUploading] = useState(false);
    const [uploadMessage, setUploadMessage] = useState<string | null>(null);

    const [immuneCellFractionInput, setImmuneCellFractionInput] = useState("20");
    const [sampleCountInput, setSampleCountInput] = useState("50");
    const [isRunning, setIsRunning] = useState(false);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);

    // Priority: a freshly uploaded file, then the cell selector's output.
    const sampleBaseName = useMemo(() => {
        if (uploadedSampleName) {
            return uploadedSampleName;
        }
        if (selectedFile) {
            return deriveSampleBaseName(selectedFile.name);
        }
        if (incomingFinalPath) {
            return deriveSampleBaseName(incomingFinalPath);
        }
        return "";
    }, [uploadedSampleName, selectedFile, incomingFinalPath]);

    const immuneCellFraction = Number.parseFloat(immuneCellFractionInput);
    const sampleCount = Number.parseInt(sampleCountInput, 10);

    const validationIssues = useMemo(() => {
        const issues: string[] = [];
        if (!sampleBaseName) {
            issues.push(
                `Upload a ${DATASET_EXTENSION} file, or arrive here from the cell selector.`,
            );
        }
        if (!Number.isFinite(immuneCellFraction)) {
            issues.push("The immune cell fraction must be a number.");
        } else if (immuneCellFraction < 0 || immuneCellFraction > 99) {
            issues.push("The immune cell fraction must be between 0 and 99.");
        }
        if (!Number.isFinite(sampleCount) || sampleCount < 1) {
            issues.push("The number of samples must be at least 1.");
        }
        return issues;
    }, [sampleBaseName, immuneCellFraction, sampleCount]);

    const canRun = validationIssues.length === 0 && !isRunning && !isUploading;

    const handleUpload = useCallback(async () => {
        if (!selectedFile) {
            return;
        }

        setIsUploading(true);
        setUploadMessage(null);
        setUploadProgressPercent(0);
        try {
            const result = await apiRegistry.tissueGenerator.uploadDataset(
                selectedFile,
                setUploadProgressPercent,
            );
            setUploadedSampleName(result.sampleBaseName);
            setUploadMessage(`Uploaded and stored as ${result.storedPath}.`);
        } catch (cause) {
            setUploadMessage(ApiError.from(cause, "The upload failed.").message);
        } finally {
            setIsUploading(false);
        }
    }, [selectedFile]);

    const handleRun = useCallback(async () => {
        if (!canRun) {
            return;
        }

        setIsRunning(true);
        setErrorMessage(null);
        try {
            const result = await apiRegistry.tissueGenerator.runSimulation({
                immuneCellFraction,
                sampleCount,
                sampleBaseName,
            });
            navigate("/tissue-generator/result", {
                replace: true,
                state: {
                    result,
                    parameters: { immuneCellFraction, sampleCount, sampleBaseName },
                },
            });
        } catch (cause) {
            setErrorMessage(ApiError.from(cause, "The simulation could not be started.").message);
        } finally {
            setIsRunning(false);
        }
    }, [canRun, immuneCellFraction, sampleCount, sampleBaseName, navigate]);

    return (
        <div className="flex flex-col gap-6">
            <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="flex flex-col gap-1">
                    <h1 className="text-2xl font-bold text-black">Synthetic tissue generator</h1>
                    <p className="text-sm text-gray-600">
                        Simulates bulk RNA-seq tissues from a single-cell dataset using SimBu.
                    </p>
                </div>
                <Link
                    to="/tissue-generator/batch"
                    className="text-sm font-medium underline hover:no-underline"
                >
                    Batch mode — many tissues at once →
                </Link>
            </div>

            {incomingFinalPath && (
                <StatusMessage tone="info">
                    Using the cell selector result:{" "}
                    <span className="font-mono">{incomingFinalPath}</span>
                </StatusMessage>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
                <Card
                    title="Input dataset"
                    description={`Upload a ${DATASET_EXTENSION} file. An upload takes priority over the cell selector output.`}
                >
                    <label className="flex flex-col gap-1">
                        <span className="text-sm font-medium">Choose a file</span>
                        <input
                            type="file"
                            accept={DATASET_EXTENSION}
                            disabled={isUploading}
                            onChange={(event) => {
                                setSelectedFile(event.target.files?.[0] ?? null);
                                setUploadedSampleName(null);
                                setUploadMessage(null);
                            }}
                            className="border border-gray-300 rounded px-3 py-2 text-sm"
                        />
                    </label>

                    <div className="text-xs text-gray-600">
                        Selected:{" "}
                        <span className="font-mono">{selectedFile?.name ?? "—"}</span>
                    </div>

                    {isUploading && (
                        <div className="flex flex-col gap-1">
                            <div className="h-2 w-full bg-gray-200 rounded">
                                <div
                                    className="h-2 bg-black rounded transition-all"
                                    style={{ width: `${uploadProgressPercent}%` }}
                                />
                            </div>
                            <span className="text-xs text-gray-600">
                                Uploading {uploadProgressPercent}% ...
                            </span>
                        </div>
                    )}

                    <Button
                        variant="primary"
                        className="h-10 px-4 justify-center w-fit"
                        onClick={handleUpload}
                        disabled={!selectedFile || isUploading}
                    >
                        {isUploading ? "Uploading ..." : "Upload"}
                    </Button>

                    {uploadMessage && <StatusMessage tone="info">{uploadMessage}</StatusMessage>}

                    <div className="text-xs text-gray-600 border-t border-gray-200 pt-3">
                        Sample name in use:{" "}
                        <span className="font-mono">{sampleBaseName || "—"}</span>
                    </div>
                </Card>

                <Card title="Simulation parameters">
                    <TextField
                        label="Immune cell fraction (0–99 %)"
                        type="number"
                        min={0}
                        max={99}
                        value={immuneCellFractionInput}
                        onChange={setImmuneCellFractionInput}
                        disabled={isRunning}
                        hint="Values above 1 are read as percentages; 0.2 and 20 both mean 20 %."
                    />

                    <TextField
                        label="Number of synthetic samples"
                        type="number"
                        min={1}
                        value={sampleCountInput}
                        onChange={setSampleCountInput}
                        disabled={isRunning}
                    />

                    {validationIssues.length > 0 && (
                        <StatusMessage tone="warning">
                            {validationIssues.map((issue) => `• ${issue}`).join("\n")}
                        </StatusMessage>
                    )}

                    {errorMessage && <StatusMessage tone="error">{errorMessage}</StatusMessage>}

                    <Button
                        variant="primary"
                        className="h-11 px-4 justify-center"
                        onClick={handleRun}
                        disabled={!canRun}
                    >
                        {isRunning ? "Running the simulation ..." : "Run the simulation"}
                    </Button>

                    {isRunning && (
                        <StatusMessage tone="info">
                            SimBu runs synchronously and can take several minutes. Please keep this
                            tab open.
                        </StatusMessage>
                    )}
                </Card>
            </div>
        </div>
    );
};

export default TissueGeneratorPage;
