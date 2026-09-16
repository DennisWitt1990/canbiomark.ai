import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "./components/layout/AppLayout";
import RequireAuthentication from "./components/RequireAuthentication";
import AccountPage from "./pages/AccountPage";
import AiSuitePage from "./pages/aisuite/AiSuitePage";
import AuditLogPage from "./pages/admin/AuditLogPage";
import DatasetImportPage from "./pages/admin/DatasetImportPage";
import UserAdministrationPage from "./pages/admin/UserAdministrationPage";
import CellSelectionDonePage from "./pages/cellselection/CellSelectionDonePage";
import CellTypePickerPage from "./pages/cellselection/CellTypePickerPage";
import ExperimentPickerPage from "./pages/cellselection/ExperimentPickerPage";
import HelpPage from "./pages/HelpPage";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import NotFoundPage from "./pages/NotFoundPage";
import SplashPage from "./pages/SplashPage";
import TissueBatchPage from "./pages/tissue/TissueBatchPage";
import TissueGeneratorPage from "./pages/tissue/TissueGeneratorPage";
import TissueResultPage from "./pages/tissue/TissueResultPage";

/**
 * The route table.
 *
 * Everything below {@link RequireAuthentication} needs a session; the admin
 * branch additionally needs the administrator role. The backend enforces both
 * independently, so these guards are a convenience, not the security boundary.
 */
const App: React.FC = () => (
    <Routes>
        {/* Public */}
        <Route path="/welcome" element={<SplashPage />} />
        <Route path="/login" element={<LoginPage />} />

        {/* Signed in */}
        <Route element={<RequireAuthentication />}>
            <Route element={<AppLayout />}>
                <Route path="/home" element={<HomePage />} />
                <Route path="/account" element={<AccountPage />} />
                <Route path="/help" element={<HelpPage />} />

                <Route path="/cell-selection" element={<ExperimentPickerPage />} />
                <Route path="/cell-selection/cell-types" element={<CellTypePickerPage />} />
                <Route path="/cell-selection/done" element={<CellSelectionDonePage />} />

                <Route path="/tissue-generator" element={<TissueGeneratorPage />} />
                <Route path="/tissue-generator/result" element={<TissueResultPage />} />
                <Route path="/tissue-generator/batch" element={<TissueBatchPage />} />

                <Route path="/ai-suite" element={<AiSuitePage />} />
            </Route>
        </Route>

        {/* Administrators only */}
        <Route element={<RequireAuthentication administratorOnly />}>
            <Route element={<AppLayout />}>
                <Route path="/admin/users" element={<UserAdministrationPage />} />
                <Route path="/admin/datasets" element={<DatasetImportPage />} />
                <Route path="/admin/audit" element={<AuditLogPage />} />
            </Route>
        </Route>

        {/* Redirects */}
        <Route path="/" element={<Navigate to="/welcome" replace />} />
        <Route path="*" element={<NotFoundPage />} />
    </Routes>
);

export default App;
