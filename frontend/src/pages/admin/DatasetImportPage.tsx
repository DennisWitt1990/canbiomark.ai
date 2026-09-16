import React, { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/ApiError";
import { apiRegistry } from "../../api/ApiRegistry";
import {
    DatasetSource,
    type DatasetSourceName,
    type ImportJob,
    type RemoteDataset,
} from "../../api/DatasetImportApi";
import Button from "../../components/Button";
import Card from "../../components/Card";
import ConfirmDialog from "../../components/ConfirmDialog";
import { Spinner } from "../../components/Spinner";
import StatusMessage from "../../components/StatusMessage";
import TextField from "../../components/TextField";
import CellTypeColumnPicker from "./CellTypeColumnPicker";

const POLL_INTERVAL_MILLISECONDS = 2000;

const ORGANISM_OPTIONS = [
    { value: "Homo sapiens", label: "Human" },
    { value: "Mus musculus", label: "Mouse" },
    { value: "", label: "Any organism" },
];

/** Search remote catalogues and import a dataset into the shared data folder. */
const DatasetImportPage: React.FC = () => {
    const [source, setSource] = useState<DatasetSourceName>(DatasetSource.CellxGene);
    const [query, setQuery] = useState("");
    const [organism, setOrganism] = useState("Homo sapiens");

    const [searchResults, setSearchResults] = useState<RemoteDataset[] | null>(null);
    const [isSearching, setIsSearching] = useState(false);
    const [searchError, setSearchError] = useState<string | null>(null);

    const [datasetToImport, setDatasetToImport] = useState<RemoteDataset | null>(null);
    const [catalogueName, setCatalogueName] = useState("");
    const [isStarting, setIsStarting] = useState(false);

    const [jobs, setJobs] = useState<ImportJob[]>([]);
    const [activeJobId, setActiveJobId] = useState<string | null>(null);
    const [jobToCancel, setJobToCancel] = useState<ImportJob | null>(null);
    const [pageError, setPageError] = useState<string | null>(null);

    const pollTimerRef = useRef<number | null>(null);

    const loadJobs = useCallback(async () => {
        try {
            setJobs(await apiRegistry.datasetImport.listImports());
        } catch (cause) {
            setPageError(ApiError.from(cause, "The imports could not be loaded.").message);
        }
    }, []);

    useEffect(() => {
        void loadJobs();
    }, [loadJobs]);

    // Poll only while something is actually moving. A job that waits for the
    // cell type confirmation needs a person, not a faster poll.
    useEffect(() => {
        const stopPolling = () => {
            if (pollTimerRef.current !== null) {
                window.clearInterval(pollTimerRef.current);
                pollTimerRef.current = null;
            }
        };

        if (!jobs.some((job) => job.shouldBePolled)) {
            stopPolling();
            return stopPolling;
        }

        pollTimerRef.current = window.setInterval(() => {
            void loadJobs();
        }, POLL_INTERVAL_MILLISECONDS);

        return stopPolling;
    }, [jobs, loadJobs]);

    const handleSearch = async (event: React.FormEvent) => {
        event.preventDefault();
        setIsSearching(true);
        setSearchError(null);
        setSearchResults(null);
        try {
            setSearchResults(
                await apiRegistry.datasetImport.search(
                    source,
                    query.trim(),
                    organism || null,
                ),
            );
        } catch (cause) {
            setSearchError(ApiError.from(cause, "The search failed.").message);
        } finally {
            setIsSearching(false);
        }
    };

    const beginImport = (dataset: RemoteDataset) => {
        setDatasetToImport(dataset);
        setCatalogueName(dataset.suggestedCatalogueName());
        setPageError(null);
    };

    const confirmImport = async () => {
        if (!datasetToImport) {
            return;
        }
        setIsStarting(true);
        setPageError(null);
        try {
            const job = await apiRegistry.datasetImport.startImport(
                datasetToImport,
                catalogueName.trim(),
            );
            setDatasetToImport(null);
            setActiveJobId(job.jobId);
            await loadJobs();
        } catch (cause) {
            setPageError(ApiError.from(cause, "The import could not be started.").message);
        } finally {
            setIsStarting(false);
        }
    };

    const cancelImport = async () => {
        if (!jobToCancel) {
            return;
        }
        try {
            await apiRegistry.datasetImport.cancelImport(jobToCancel.jobId);
            if (activeJobId === jobToCancel.jobId) {
                setActiveJobId(null);
            }
            setJobToCancel(null);
            await loadJobs();
        } catch (cause) {
            setPageError(ApiError.from(cause, "The import could not be cancelled.").message);
        }
    };

    const waitingJob = jobs.find(
        (job) => job.isWaitingForUser && (activeJobId === null || job.jobId === activeJobId),
    );

    return (
        <div className="flex flex-col gap-6">
            <div className="flex flex-col gap-1">
                <h1 className="text-2xl font-bold text-black">Import datasets</h1>
                <p className="text-sm text-gray-600">
                    Find single-cell datasets online and publish them to the shared
                    catalogue that every user's cell selector reads from.
                </p>
            </div>

            {pageError && <StatusMessage tone="error">{pageError}</StatusMessage>}

            {waitingJob && (
                <CellTypeColumnPicker
                    jobId={waitingJob.jobId}
                    onConfirmed={() => void loadJobs()}
                    onCancel={() => setJobToCancel(waitingJob)}
                />
            )}

            <Card title="Search">
                <form onSubmit={handleSearch} className="flex flex-col gap-4">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <label className="flex flex-col gap-1">
                            <span className="text-sm font-medium text-black">Source</span>
                            <select
                                value={source}
                                onChange={(event) =>
                                    setSource(event.target.value as DatasetSourceName)
                                }
                                className="border border-gray-300 rounded px-3 py-2 outline-none focus:ring-2 focus:ring-black"
                            >
                                <option value={DatasetSource.CellxGene}>
                                    CELLxGENE Discover (browse)
                                </option>
                                <option value={DatasetSource.EbiBioStudies}>
                                    EBI BioStudies (by accession)
                                </option>
                            </select>
                        </label>

                        <TextField
                            label={
                                source === DatasetSource.CellxGene
                                    ? "Search terms"
                                    : "Accession"
                            }
                            value={query}
                            onChange={setQuery}
                            placeholder={
                                source === DatasetSource.CellxGene
                                    ? "liver carcinoma"
                                    : "E-MTAB-10553"
                            }
                            hint={
                                source === DatasetSource.CellxGene
                                    ? "Matches title, tissue, disease and assay."
                                    : "BioStudies free-text search returns publications, so only accessions are accepted."
                            }
                        />

                        {source === DatasetSource.CellxGene && (
                            <label className="flex flex-col gap-1">
                                <span className="text-sm font-medium text-black">Organism</span>
                                <select
                                    value={organism}
                                    onChange={(event) => setOrganism(event.target.value)}
                                    className="border border-gray-300 rounded px-3 py-2 outline-none focus:ring-2 focus:ring-black"
                                >
                                    {ORGANISM_OPTIONS.map((option) => (
                                        <option key={option.label} value={option.value}>
                                            {option.label}
                                        </option>
                                    ))}
                                </select>
                            </label>
                        )}
                    </div>

                    <Button
                        type="submit"
                        variant="primary"
                        className="h-10 px-4 justify-center w-fit"
                        disabled={isSearching}
                    >
                        {isSearching ? "Searching ..." : "Search"}
                    </Button>
                </form>

                {searchError && <StatusMessage tone="error">{searchError}</StatusMessage>}

                {isSearching && (
                    <div className="flex items-center gap-3 text-sm text-gray-600 py-4">
                        <Spinner className="h-6 w-6" />
                        Querying the remote catalogue ...
                    </div>
                )}

                {searchResults !== null && !isSearching && (
                    <div className="flex flex-col gap-2">
                        <p className="text-xs text-gray-500">
                            {searchResults.length} dataset(s) found.
                        </p>
                        {searchResults.map((dataset) => (
                            <SearchResultRow
                                key={`${dataset.datasetId}-${dataset.title}`}
                                dataset={dataset}
                                onImport={() => beginImport(dataset)}
                            />
                        ))}
                    </div>
                )}
            </Card>

            <Card
                title="Imports"
                actions={
                    <Button variant="secondary" className="h-9 px-3" onClick={loadJobs}>
                        Refresh
                    </Button>
                }
            >
                {jobs.length === 0 ? (
                    <p className="text-sm text-gray-600">No import has been started yet.</p>
                ) : (
                    <ul className="flex flex-col gap-2">
                        {jobs.map((job) => (
                            <ImportJobRow
                                key={job.jobId}
                                job={job}
                                onShow={() => setActiveJobId(job.jobId)}
                                onCancel={() => setJobToCancel(job)}
                            />
                        ))}
                    </ul>
                )}
            </Card>

            {datasetToImport && (
                <ConfirmDialog
                    title="Import this dataset?"
                    busy={isStarting}
                    confirmLabel="Start the import"
                    message={
                        <div className="flex flex-col gap-3">
                            <p>
                                <strong>{datasetToImport.title}</strong>
                                {datasetToImport.fileSizeLabel && (
                                    <> — {datasetToImport.fileSizeLabel}</>
                                )}
                            </p>
                            <TextField
                                label="Catalogue name"
                                value={catalogueName}
                                onChange={setCatalogueName}
                                hint="Becomes combined_adata_<name>.h5ad in the shared folder. Lower case, letters, digits, _ and - only."
                            />
                            <p className="text-xs text-gray-600">
                                The file is downloaded and converted for anndata 0.7.6, which
                                SimBu requires. You will be asked to confirm the cell type
                                column before it is published.
                            </p>
                        </div>
                    }
                    onConfirm={confirmImport}
                    onCancel={() => setDatasetToImport(null)}
                />
            )}

            {jobToCancel && (
                <ConfirmDialog
                    title="Cancel this import?"
                    isDestructive
                    confirmLabel="Cancel the import"
                    message={
                        <>
                            The import of <strong>{jobToCancel.datasetTitle}</strong> stops and
                            everything downloaded so far is discarded.
                        </>
                    }
                    onConfirm={cancelImport}
                    onCancel={() => setJobToCancel(null)}
                />
            )}
        </div>
    );
};

const SearchResultRow: React.FC<{
    dataset: RemoteDataset;
    onImport: () => void;
}> = ({ dataset, onImport }) => (
    <div className="border border-gray-200 rounded p-3 flex items-start justify-between gap-4 flex-wrap">
        <div className="flex flex-col gap-1 min-w-0">
            <span className="text-sm font-medium">{dataset.title}</span>
            {dataset.collectionName && dataset.collectionName !== dataset.title && (
                <span className="text-xs text-gray-500">{dataset.collectionName}</span>
            )}
            <div className="flex flex-wrap gap-1 pt-1">
                {[...dataset.tissues.slice(0, 3), ...dataset.diseases.slice(0, 2)].map(
                    (label) => (
                        <span
                            key={label}
                            className="text-xs px-2 py-0.5 rounded bg-gray-100 text-gray-800"
                        >
                            {label}
                        </span>
                    ),
                )}
            </div>
            <div className="text-xs text-gray-500 pt-1 flex flex-wrap gap-3">
                <span>{dataset.organisms.join(", ") || "unknown organism"}</span>
                {dataset.assays.length > 0 && <span>{dataset.assays[0]}</span>}
                {dataset.fileSizeLabel && <span>{dataset.fileSizeLabel}</span>}
                {dataset.landingPageUrl && (
                    <a
                        href={dataset.landingPageUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="underline hover:no-underline"
                    >
                        Source page
                    </a>
                )}
            </div>
        </div>
        <Button variant="secondary" className="h-9 px-3 shrink-0" onClick={onImport}>
            Import
        </Button>
    </div>
);

const ImportJobRow: React.FC<{
    job: ImportJob;
    onShow: () => void;
    onCancel: () => void;
}> = ({ job, onShow, onCancel }) => (
    <li className="border border-gray-200 rounded p-3 flex flex-col gap-2">
        <div className="flex items-start justify-between gap-3 flex-wrap">
            <div className="flex flex-col min-w-0">
                <span className="text-sm font-medium">{job.datasetTitle}</span>
                <span className="text-xs text-gray-500 font-mono">
                    {job.catalogueName}
                </span>
            </div>
            <div className="flex items-center gap-2">
                <StageBadge job={job} />
                {job.isWaitingForUser && (
                    <Button variant="primary" className="h-8 px-3" onClick={onShow}>
                        Choose the column
                    </Button>
                )}
                {job.isActive && (
                    <Button variant="danger" className="h-8 px-3" onClick={onCancel}>
                        Cancel
                    </Button>
                )}
            </div>
        </div>

        {job.isActive && !job.isWaitingForUser && (
            <div className="h-1.5 w-full bg-gray-200 rounded">
                <div
                    className="h-1.5 bg-black rounded transition-all"
                    style={{ width: `${job.completedPercent}%` }}
                />
            </div>
        )}

        <p className="text-xs text-gray-600">{job.message}</p>

        {job.errorMessage && (
            <p className="text-xs text-red-700 whitespace-pre-wrap">{job.errorMessage}</p>
        )}

        {job.isFinished && job.publishedFileName && (
            <p className="text-xs text-emerald-700">
                Published as <span className="font-mono">{job.publishedFileName}</span>
                {job.selectedCellTypeColumn && (
                    <>
                        {" "}
                        · cell type from{" "}
                        <span className="font-mono">{job.selectedCellTypeColumn}</span>
                        {job.distinctCellTypeCount !== null && (
                            <> ({job.distinctCellTypeCount} types)</>
                        )}
                    </>
                )}
            </p>
        )}
    </li>
);

const StageBadge: React.FC<{ job: ImportJob }> = ({ job }) => {
    const toneClassName = job.hasFailed
        ? "bg-red-50 text-red-700 border-red-200"
        : job.isFinished
          ? "bg-emerald-50 text-emerald-700 border-emerald-200"
          : job.isWaitingForUser
            ? "bg-amber-50 text-amber-800 border-amber-200"
            : "bg-blue-50 text-blue-700 border-blue-200";

    return (
        <span className={`text-xs px-2 py-1 rounded-full border ${toneClassName}`}>
            {job.stageLabel}
        </span>
    );
};

export default DatasetImportPage;
