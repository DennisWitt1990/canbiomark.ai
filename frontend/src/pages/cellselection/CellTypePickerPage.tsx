import React, { useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../../api/ApiError";
import { apiRegistry } from "../../api/ApiRegistry";
import type { CellTypePreview } from "../../api/CellSelectionApi";
import Button from "../../components/Button";
import Card from "../../components/Card";
import StatusMessage from "../../components/StatusMessage";

/** Step 2 of the cell selector: keep the cell types you want per experiment. */
const CellTypePickerPage: React.FC = () => {
    const navigate = useNavigate();
    const location = useLocation();
    const mergeResult = location.state as CellTypePreview | null;

    const cellTypesByExperiment = useMemo(
        () => mergeResult?.cellTypesByExperiment ?? {},
        [mergeResult],
    );

    const [selectionByExperiment, setSelectionByExperiment] = useState<
        Record<string, string[]>
    >(() =>
        Object.fromEntries(
            Object.keys(mergeResult?.cellTypesByExperiment ?? {}).map((name) => [name, []]),
        ),
    );
    const [isFiltering, setIsFiltering] = useState(false);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);

    const experimentNames = Object.keys(cellTypesByExperiment);

    const everyExperimentHasASelection =
        experimentNames.length > 0 &&
        experimentNames.every((name) => (selectionByExperiment[name]?.length ?? 0) > 0);

    const toggleCellType = (experimentName: string, cellType: string) => {
        setSelectionByExperiment((previousSelection) => {
            const currentCellTypes = previousSelection[experimentName] ?? [];
            const nextCellTypes = currentCellTypes.includes(cellType)
                ? currentCellTypes.filter((name) => name !== cellType)
                : [...currentCellTypes, cellType];
            return { ...previousSelection, [experimentName]: nextCellTypes };
        });
    };

    const selectAll = (experimentName: string) =>
        setSelectionByExperiment((previousSelection) => ({
            ...previousSelection,
            [experimentName]: [...(cellTypesByExperiment[experimentName] ?? [])],
        }));

    const clearAll = (experimentName: string) =>
        setSelectionByExperiment((previousSelection) => ({
            ...previousSelection,
            [experimentName]: [],
        }));

    const handleFilter = async () => {
        if (!mergeResult || !everyExperimentHasASelection) {
            return;
        }

        setIsFiltering(true);
        setErrorMessage(null);
        try {
            const finalPath = await apiRegistry.cellSelection.createSelectedDataset(
                mergeResult.experimentIds,
                selectionByExperiment,
            );
            navigate("/cell-selection/done", { state: { finalPath } });
        } catch (cause) {
            setErrorMessage(ApiError.from(cause, "The dataset could not be filtered.").message);
        } finally {
            setIsFiltering(false);
        }
    };

    if (!mergeResult || experimentNames.length === 0) {
        return (
            <Card title="No experiments selected">
                <p className="text-sm text-gray-600">
                    Please start from the experiment
                    selection.
                </p>
                <Button
                    variant="primary"
                    className="h-10 px-4 w-fit justify-center"
                    route="/cell-selection"
                >
                    Back to the experiments
                </Button>
            </Card>
        );
    }

    return (
        <div className="flex flex-col gap-6">
            <div className="flex flex-col gap-1">
                <h1 className="text-2xl font-bold text-black">Cell selector</h1>
                <p className="text-sm text-gray-600">
                    Step 2: Choose at least one cell type per experiment. Only the selected cells
                    will be merged into the final dataset.
                </p>
            </div>

            {errorMessage && <StatusMessage tone="error">{errorMessage}</StatusMessage>}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {experimentNames.map((experimentName) => {
                    const availableCellTypes = cellTypesByExperiment[experimentName] ?? [];
                    const selectedCellTypes = selectionByExperiment[experimentName] ?? [];

                    return (
                        <Card
                            key={experimentName}
                            title={experimentName}
                            description={`${selectedCellTypes.length} of ${availableCellTypes.length} cell types selected`}
                        >
                            <div
                                role="listbox"
                                aria-multiselectable="true"
                                className="border border-gray-200 rounded p-2 h-80 overflow-y-auto space-y-1"
                            >
                                {availableCellTypes.map((cellType) => {
                                    const isSelected = selectedCellTypes.includes(cellType);
                                    return (
                                        <button
                                            key={cellType}
                                            type="button"
                                            role="option"
                                            aria-selected={isSelected}
                                            onClick={() => toggleCellType(experimentName, cellType)}
                                            className={`block w-full text-left px-3 py-2 rounded border transition ${
                                                isSelected
                                                    ? "bg-black text-white border-black"
                                                    : "bg-white text-gray-900 border-gray-300 hover:bg-gray-50"
                                            }`}
                                        >
                                            {cellType}
                                        </button>
                                    );
                                })}
                            </div>

                            <div className="flex gap-2">
                                <Button
                                    variant="secondary"
                                    className="h-9 px-3"
                                    onClick={() => selectAll(experimentName)}
                                    disabled={
                                        selectedCellTypes.length === availableCellTypes.length
                                    }
                                >
                                    Select all
                                </Button>
                                <Button
                                    variant="secondary"
                                    className="h-9 px-3"
                                    onClick={() => clearAll(experimentName)}
                                    disabled={selectedCellTypes.length === 0}
                                >
                                    Clear
                                </Button>
                            </div>
                        </Card>
                    );
                })}
            </div>

            <Button
                variant="tertiary"
                className="h-11 px-6 justify-center w-fit self-center"
                onClick={handleFilter}
                disabled={!everyExperimentHasASelection || isFiltering}
            >
                {isFiltering ? "Creating dataset ..." : "Create the final dataset"}
            </Button>
        </div>
    );
};

export default CellTypePickerPage;
