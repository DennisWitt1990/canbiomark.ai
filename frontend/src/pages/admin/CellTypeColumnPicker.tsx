import React, { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/ApiError";
import { apiRegistry } from "../../api/ApiRegistry";
import type { CellTypeDecision, ColumnCandidate } from "../../api/DatasetImportApi";
import Button from "../../components/Button";
import Card from "../../components/Card";
import { Spinner } from "../../components/Spinner";
import StatusMessage from "../../components/StatusMessage";

interface CellTypeColumnPickerProps {
    jobId: string;
    onConfirmed: () => void;
    onCancel: () => void;
}

/**
 * Lets an administrator confirm which `obs` column holds the cell type.
 *
 * The preview shows the **most frequent** values rather than the first rows on
 * purpose: in real datasets the first cells are often unlabelled (E-HCAD-10 has
 * 21.9 % empty labels and its first three cells are all blank), so a raw head()
 * would show three empty strings and tell the reader nothing.
 */
const CellTypeColumnPicker: React.FC<CellTypeColumnPickerProps> = ({
    jobId,
    onConfirmed,
    onCancel,
}) => {
    const [decision, setDecision] = useState<CellTypeDecision | null>(null);
    const [selectedColumn, setSelectedColumn] = useState<string | null>(null);
    const [showUnusableColumns, setShowUnusableColumns] = useState(false);
    const [isLoading, setIsLoading] = useState(true);
    const [isConfirming, setIsConfirming] = useState(false);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);

    useEffect(() => {
        let isStillMounted = true;

        apiRegistry.datasetImport
            .getCellTypeDecision(jobId)
            .then((loadedDecision) => {
                if (!isStillMounted) {
                    return;
                }
                setDecision(loadedDecision);
                setSelectedColumn(loadedDecision.recommendedColumn);
            })
            .catch((cause) =>
                setErrorMessage(
                    ApiError.from(cause, "The columns could not be read.").message,
                ),
            )
            .finally(() => isStillMounted && setIsLoading(false));

        return () => {
            isStillMounted = false;
        };
    }, [jobId]);

    const { usableCandidates, unusableCandidates } = useMemo(() => {
        const candidates = decision?.candidates ?? [];
        return {
            usableCandidates: candidates.filter((candidate) => candidate.isUsable),
            unusableCandidates: candidates.filter((candidate) => !candidate.isUsable),
        };
    }, [decision]);

    const handleConfirm = async () => {
        if (!selectedColumn) {
            return;
        }
        setIsConfirming(true);
        setErrorMessage(null);
        try {
            await apiRegistry.datasetImport.confirmCellTypeColumn(jobId, selectedColumn);
            onConfirmed();
        } catch (cause) {
            setErrorMessage(
                ApiError.from(cause, "The column could not be confirmed.").message,
            );
        } finally {
            setIsConfirming(false);
        }
    };

    if (isLoading) {
        return (
            <Card title="Reading the dataset metadata">
                <div className="flex items-center gap-3 text-sm text-gray-600 py-4">
                    <Spinner className="h-6 w-6" />
                    Reading the observation columns ...
                </div>
            </Card>
        );
    }

    if (!decision) {
        return (
            <Card title="Choose the cell type column">
                {errorMessage && <StatusMessage tone="error">{errorMessage}</StatusMessage>}
                <Button variant="secondary" className="h-10 px-4 w-fit" onClick={onCancel}>
                    Back
                </Button>
            </Card>
        );
    }

    return (
        <Card
            title="Which column holds the cell type?"
            description={decision.datasetTitle}
            actions={
                <Button variant="secondary" className="h-9 px-3" onClick={onCancel}>
                    Cancel the import
                </Button>
            }
        >
            {decision.recommendedColumn ? (
                <StatusMessage tone="info">
                    Suggested: <strong>{decision.recommendedColumn}</strong>. Check the values
                    below before confirming — several columns can look plausible, and the
                    finest-grained one is not always the right one.
                </StatusMessage>
            ) : (
                <StatusMessage tone="warning">
                    No column could be identified as a cell type. Nothing is preselected on
                    purpose: a wrong cell type does not fail loudly, it produces simulations
                    that run perfectly and mean nothing. Pick a column only if you know it
                    carries cell type labels, otherwise cancel this import.
                </StatusMessage>
            )}

            {errorMessage && <StatusMessage tone="error">{errorMessage}</StatusMessage>}

            <div className="overflow-x-auto">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="text-left text-gray-500 border-b border-gray-200">
                            <th className="py-2 pr-3 font-medium w-8" />
                            <th className="py-2 pr-3 font-medium">Column</th>
                            <th className="py-2 pr-3 font-medium">Distinct</th>
                            <th className="py-2 pr-3 font-medium">Missing</th>
                            <th className="py-2 font-medium">Most frequent values</th>
                        </tr>
                    </thead>
                    <tbody>
                        {usableCandidates.map((candidate) => (
                            <CandidateRow
                                key={candidate.columnName}
                                candidate={candidate}
                                isSelected={selectedColumn === candidate.columnName}
                                isRecommended={
                                    decision.recommendedColumn === candidate.columnName
                                }
                                onSelect={() => setSelectedColumn(candidate.columnName)}
                            />
                        ))}
                    </tbody>
                </table>
            </div>

            {usableCandidates.length === 0 && (
                <p className="text-sm text-gray-600">
                    No column in this dataset is usable as a cell type.
                </p>
            )}

            {unusableCandidates.length > 0 && (
                <details
                    open={showUnusableColumns}
                    onToggle={(event) =>
                        setShowUnusableColumns((event.target as HTMLDetailsElement).open)
                    }
                    className="text-sm"
                >
                    <summary className="cursor-pointer text-gray-600">
                        {unusableCandidates.length} column(s) ruled out — show why
                    </summary>
                    <ul className="pt-2 flex flex-col gap-2">
                        {unusableCandidates.map((candidate) => (
                            <li
                                key={candidate.columnName}
                                className="border border-gray-200 rounded p-2 text-xs"
                            >
                                <div className="font-mono">{candidate.columnName}</div>
                                <div className="text-gray-600">
                                    {candidate.reasons.join(" ")}
                                </div>
                                {candidate.previewValues.length > 0 && (
                                    <div className="text-gray-500">
                                        values: {candidate.previewValues.join(", ")}
                                    </div>
                                )}
                            </li>
                        ))}
                    </ul>
                </details>
            )}

            <div className="flex items-center gap-3 border-t border-gray-200 pt-4">
                <Button
                    variant="primary"
                    className="h-10 px-4 justify-center"
                    onClick={handleConfirm}
                    disabled={!selectedColumn || isConfirming}
                >
                    {isConfirming ? "Confirming ..." : "Confirm and continue"}
                </Button>
                {selectedColumn && (
                    <span className="text-xs text-gray-600">
                        The import will set <span className="font-mono">cell_type</span> from{" "}
                        <span className="font-mono">{selectedColumn}</span>.
                    </span>
                )}
            </div>
        </Card>
    );
};

interface CandidateRowProps {
    candidate: ColumnCandidate;
    isSelected: boolean;
    isRecommended: boolean;
    onSelect: () => void;
}

const CandidateRow: React.FC<CandidateRowProps> = ({
    candidate,
    isSelected,
    isRecommended,
    onSelect,
}) => (
    <tr
        onClick={onSelect}
        className={`border-b border-gray-100 cursor-pointer ${
            isSelected ? "bg-gray-50" : "hover:bg-gray-50"
        }`}
    >
        <td className="py-2 pr-3">
            <input
                type="radio"
                checked={isSelected}
                onChange={onSelect}
                aria-label={`Use ${candidate.columnName}`}
            />
        </td>
        <td className="py-2 pr-3">
            <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-xs break-all">{candidate.columnName}</span>
                {isRecommended && (
                    <span className="text-xs px-2 py-0.5 rounded-full border bg-black text-white border-black">
                        suggested
                    </span>
                )}
                {candidate.isKnownName && !isRecommended && (
                    <span className="text-xs px-2 py-0.5 rounded-full border bg-white text-gray-700 border-gray-300">
                        known name
                    </span>
                )}
            </div>
        </td>
        <td className="py-2 pr-3 whitespace-nowrap">{candidate.distinctValueCount}</td>
        <td className="py-2 pr-3 whitespace-nowrap">
            <span
                className={
                    candidate.missingFraction > 0.2 ? "text-amber-700" : "text-gray-600"
                }
            >
                {candidate.missingPercentLabel}
            </span>
        </td>
        <td className="py-2">
            <div className="flex flex-wrap gap-1">
                {candidate.mostFrequentValues.slice(0, 4).map((entry) => (
                    <span
                        key={entry.value}
                        title={`${entry.count} cells`}
                        className="text-xs px-2 py-0.5 rounded bg-gray-100 text-gray-800"
                    >
                        {entry.value}
                    </span>
                ))}
            </div>
        </td>
    </tr>
);

export default CellTypeColumnPicker;
