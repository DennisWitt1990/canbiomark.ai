import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../../api/ApiError";
import { apiRegistry } from "../../api/ApiRegistry";
import type { Experiment } from "../../api/CellSelectionApi";
import Button from "../../components/Button";
import Card from "../../components/Card";
import { Spinner } from "../../components/Spinner";
import StatusMessage from "../../components/StatusMessage";

const REQUIRED_EXPERIMENT_COUNT = 2;

/** Step 1 of the cell selector: choose experiments, then inspect their cell types. */
const ExperimentPickerPage: React.FC = () => {
    const navigate = useNavigate();

    const [experiments, setExperiments] = useState<Experiment[]>([]);
    const [selectedExperimentIds, setSelectedExperimentIds] = useState<number[]>([]);
    const [searchTerm, setSearchTerm] = useState("");
    const [isLoading, setIsLoading] = useState(true);
    const [isMerging, setIsMerging] = useState(false);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);

    const loadExperiments = useCallback(async () => {
        setIsLoading(true);
        setErrorMessage(null);
        try {
            setExperiments(await apiRegistry.cellSelection.listExperiments());
        } catch (cause) {
            setErrorMessage(
                ApiError.from(cause, "The experiments could not be loaded.").message,
            );
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        void loadExperiments();
    }, [loadExperiments]);

    const filteredExperiments = useMemo(
        () => experiments.filter((experiment) => experiment.matches(searchTerm)),
        [experiments, searchTerm],
    );

    const toggleExperiment = (experimentId: number) => {
        setSelectedExperimentIds((previousIds) => {
            if (previousIds.includes(experimentId)) {
                return previousIds.filter((id) => id !== experimentId);
            }
            if (previousIds.length >= REQUIRED_EXPERIMENT_COUNT) {
                return previousIds;
            }
            return [...previousIds, experimentId];
        });
    };

    const labelFor = (experimentId: number | undefined): string => {
        if (experimentId === undefined) {
            return "—";
        }
        return (
            experiments.find((experiment) => experiment.experimentId === experimentId)
                ?.displayLabel ?? "—"
        );
    };

    const canMerge =
        selectedExperimentIds.length === REQUIRED_EXPERIMENT_COUNT && !isMerging;

    const handleMerge = async () => {
        if (!canMerge) {
            return;
        }

        setIsMerging(true);
        setErrorMessage(null);
        try {
            const mergeResult = await apiRegistry.cellSelection.previewCellTypes(
                selectedExperimentIds,
            );
            navigate("/cell-selection/cell-types", { state: mergeResult });
        } catch (cause) {
            setErrorMessage(ApiError.from(cause, "The cell types could not be loaded.").message);
        } finally {
            setIsMerging(false);
        }
    };

    return (
        <div className="flex flex-col gap-6">
            <div className="flex flex-col gap-1">
                <h1 className="text-2xl font-bold text-black">Cell selector</h1>
                <p className="text-sm text-gray-600">
                    Step 1: Choose exactly {REQUIRED_EXPERIMENT_COUNT} experiments. Next, select
                    the cell types to keep from each experiment.
                </p>
            </div>

            {errorMessage && <StatusMessage tone="error">{errorMessage}</StatusMessage>}

            <Card
                title="Available experiments"
                actions={
                    <div className="flex items-center gap-2">
                        <input
                            type="search"
                            value={searchTerm}
                            placeholder="Search for a tissue or experiment ..."
                            onChange={(event) => setSearchTerm(event.target.value)}
                            className="border border-gray-300 rounded px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black"
                        />
                        <span className="text-sm text-gray-500 whitespace-nowrap">
                            {filteredExperiments.length} / {experiments.length}
                        </span>
                    </div>
                }
            >
                {isLoading ? (
                    <div className="flex items-center gap-3 text-sm text-gray-600 py-6">
                        <Spinner className="h-6 w-6" />
                        Loading the catalogue ...
                    </div>
                ) : filteredExperiments.length === 0 ? (
                    <p className="text-sm text-gray-600 py-4">
                        No experiment matches. The catalogue is read from the shared data
                        directory on the server.
                    </p>
                ) : (
                    <div
                        role="listbox"
                        aria-multiselectable="true"
                        className="border border-gray-200 rounded p-2 h-96 overflow-y-auto space-y-1"
                    >
                        {filteredExperiments.map((experiment) => {
                            const isSelected = selectedExperimentIds.includes(
                                experiment.experimentId,
                            );
                            return (
                                <button
                                    key={experiment.experimentId}
                                    type="button"
                                    role="option"
                                    aria-selected={isSelected}
                                    onClick={() => toggleExperiment(experiment.experimentId)}
                                    className={`w-full text-left px-3 py-2 rounded border transition ${
                                        isSelected
                                            ? "bg-black text-white border-black"
                                            : "bg-white text-gray-900 border-gray-300 hover:bg-gray-50"
                                    }`}
                                >
                                    {experiment.displayLabel}
                                </button>
                            );
                        })}
                    </div>
                )}

                <div className="flex flex-wrap items-center justify-between gap-4 pt-2">
                    <Button
                        variant="secondary"
                        className="h-10 px-3 justify-center"
                        onClick={() => setSelectedExperimentIds([])}
                        disabled={selectedExperimentIds.length === 0 || isMerging}
                    >
                        Clear the selection
                    </Button>

                    <div className="text-sm text-gray-700">
                        <div>
                            <span className="font-medium">Experiment 1:</span>{" "}
                            {labelFor(selectedExperimentIds[0])}
                        </div>
                        <div>
                            <span className="font-medium">Experiment 2:</span>{" "}
                            {labelFor(selectedExperimentIds[1])}
                        </div>
                    </div>

                    <Button
                        variant="tertiary"
                        className="h-10 px-4 justify-center"
                        onClick={handleMerge}
                        disabled={!canMerge}
                    >
                        {isMerging ? "Loading cell types ..." : "Next: choose cell types"}
                    </Button>
                </div>

                {isMerging && (
                    <StatusMessage tone="info">
                        Reading the cell types from the selected experiments.
                    </StatusMessage>
                )}
            </Card>
        </div>
    );
};

export default ExperimentPickerPage;
