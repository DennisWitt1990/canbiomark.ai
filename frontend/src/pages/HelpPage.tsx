import React from "react";
import Card from "../components/Card";
import { useAuthentication } from "../context/AuthenticationContext";

interface HelpSection {
    title: string;
    paragraphs: string[];
    administratorOnly?: boolean;
}

const HELP_SECTIONS: HelpSection[] = [
    {
        title: "Signing in",
        paragraphs: [
            "You sign in with a username and a password. Accounts are created by an administrator; there is no self-registration.",
            "If an administrator created or reset your account, you are asked to choose your own password at the next sign-in. You can change it at any time under 'Your account'.",
            "Changing your password signs you out of every device, which is intended: it ends any session someone else might still hold.",
        ],
    },
    {
        title: "Cell selector",
        paragraphs: [
            "Choose exactly two experiments from the shared catalogue. The cell types found in each are listed before merging.",
            "Then keep the cell types you want per experiment. Only your selected cells are merged. The result is written to your workspace as a .h5ad file that the tissue generator can read directly.",
            "Large datasets take a few minutes to merge. Keep the tab open while it runs.",
        ],
    },
    {
        title: "Synthetic tissue generator",
        paragraphs: [
            "Simulates bulk RNA-seq tissues from a single-cell dataset using SimBu. Either continue straight from the cell selector, or upload your own .h5ad file.",
            "The immune cell fraction accepts both percentages and ratios: 20 and 0.2 both mean 20 %. Note that a plain 1 is read as 100 % (and capped at 99 %) — write 0.01 if you mean one percent.",
            "Batch mode runs many simulations from a single .csv or .tsv file. Validate the file first; the server checks that every referenced dataset exists before anything starts.",
            "Within one batch, each distinct input dataset is copied once and its Seurat conversion is cached, so a batch over fifty fractions does not convert the same file fifty times.",
        ],
    },
    {
        title: "AI suite",
        paragraphs: [
            "Trains one H2O deep-learning classifier per threshold and evaluates it on your test data, both as-is and on a class-balanced subsample.",
            "Upload one folder of SimBu .txt files per split. The label of each file is read from its name, so keep the SimBu naming (for example simbu_icf_0.02.txt).",
            "Thresholds where the binarised label would be constant in train or test are skipped, because a classifier cannot be fitted on a single class. Skipped thresholds are listed in their own sheet of the Excel report rather than dropped silently.",
        ],
    },
    {
        title: "Your workspace",
        paragraphs: [
            "Every user has a private workspace on the server. Uploads and results live there and are not visible to anybody else.",
            "Your storage quota is shown under 'Your account'. Contact an administrator if you need more room.",
        ],
    },
    {
        title: "User administration",
        administratorOnly: true,
        paragraphs: [
            "Under 'User administration' you create accounts, set roles and quotas, reset passwords, end sessions and delete accounts.",
            "An initial or reset password is shown exactly once — it is stored only as a salted hash and cannot be recovered afterwards. Copy it and pass it on securely.",
            "Disabling an account or resetting its password ends its running sessions immediately.",
            "The server refuses any change that would leave the installation without an active administrator, so you cannot lock yourself out.",
            "The audit trail records sign-ins, failed attempts and every administrative change.",
        ],
    },
];

/** Static help text for every module. */
const HelpPage: React.FC = () => {
    const { currentUser } = useAuthentication();

    const visibleSections = HELP_SECTIONS.filter(
        (section) => !section.administratorOnly || currentUser?.isAdministrator,
    );

    return (
        <div className="flex flex-col gap-6">
            <div className="flex flex-col gap-1">
                <h1 className="text-2xl font-bold text-black">Help</h1>
                <p className="text-sm text-gray-600">
                    How the modules work and what to watch out for.
                </p>
            </div>

            {visibleSections.map((section) => (
                <Card key={section.title} title={section.title}>
                    <div className="flex flex-col gap-2">
                        {section.paragraphs.map((paragraph) => (
                            <p key={paragraph} className="text-sm text-gray-700">
                                {paragraph}
                            </p>
                        ))}
                    </div>
                </Card>
            ))}
        </div>
    );
};

export default HelpPage;
