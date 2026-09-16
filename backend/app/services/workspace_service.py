"""Per-user file storage.

Every path the API accepts from a browser is *relative to the owning user's
workspace*.  :class:`UserWorkspace` is the single gate that turns such a
relative path into an absolute one, and it refuses anything that would escape
the workspace.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from ..domain.errors import ValidationError, WorkspaceViolationError


@dataclass(frozen=True)
class UserWorkspace:
    """The private directory tree of one user."""

    user_id: str
    root_directory: Path

    # -- sub directories used by the individual modules ---------------------

    @property
    def cell_selection_directory(self) -> Path:
        return self.ensure_directory("cell_selection")

    @property
    def tissue_uploads_directory(self) -> Path:
        return self.ensure_directory("tissue_generator/uploads")

    @property
    def tissue_runs_directory(self) -> Path:
        return self.ensure_directory("tissue_generator/runs")

    @property
    def tissue_batches_directory(self) -> Path:
        return self.ensure_directory("tissue_generator/batches")

    @property
    def ai_suite_directory(self) -> Path:
        return self.ensure_directory("ai_suite")

    # -- path handling ------------------------------------------------------

    def ensure_directory(self, relative_path: str) -> Path:
        directory = self.resolve(relative_path, must_exist=False)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def resolve(self, relative_path: str, must_exist: bool = True) -> Path:
        """Turn a workspace-relative path into a validated absolute path."""
        sanitized = self.sanitize_relative_path(relative_path)
        absolute_path = (self.root_directory / sanitized).resolve()
        self.assert_inside(absolute_path)

        if must_exist and not absolute_path.exists():
            from ..domain.errors import ResourceNotFoundError

            raise ResourceNotFoundError(f"'{sanitized}' does not exist in your workspace.")
        return absolute_path

    def to_relative_path(self, absolute_path: Path) -> str:
        """Inverse of :meth:`resolve`; used for every path returned to the browser."""
        resolved = Path(absolute_path).resolve()
        self.assert_inside(resolved)
        return str(resolved.relative_to(self.root_directory.resolve()))

    def assert_inside(self, absolute_path: Path) -> None:
        workspace_root = self.root_directory.resolve()
        resolved = Path(absolute_path).resolve()
        if resolved != workspace_root and workspace_root not in resolved.parents:
            raise WorkspaceViolationError(
                "The requested path lies outside your workspace."
            )

    def list_files_recursively(self, directory: Path) -> List[str]:
        """All files below ``directory``, as paths relative to that directory."""
        self.assert_inside(directory)
        if not directory.exists():
            return []
        return sorted(
            str(entry.relative_to(directory))
            for entry in directory.rglob("*")
            if entry.is_file()
        )

    def used_bytes(self) -> int:
        """Total size of the workspace on disk."""
        return sum(
            entry.stat().st_size
            for entry in self.root_directory.rglob("*")
            if entry.is_file()
        )

    def delete_tree(self, directory: Path) -> None:
        self.assert_inside(directory)
        shutil.rmtree(directory, ignore_errors=True)

    # -- validation ---------------------------------------------------------

    @staticmethod
    def sanitize_relative_path(relative_path: str) -> str:
        """Reject traversal, absolute paths and Windows drive letters.

        An absolute path is refused rather than quietly reinterpreted as a
        relative one: silently turning ``/etc/passwd`` into
        ``<workspace>/etc/passwd`` would be contained but confusing, and it
        hides a caller bug instead of reporting it.
        """
        candidate = (relative_path or "").strip().replace("\\", "/")
        if not candidate:
            raise ValidationError("A relative path is required.")
        if candidate.startswith("/"):
            raise ValidationError("Absolute paths are not accepted.")
        if ":" in candidate:
            raise ValidationError("Drive letters and URLs are not accepted.")
        if candidate == ".." or candidate.startswith("../") or "/../" in candidate:
            raise ValidationError("Relative paths must not contain '..'.")
        return candidate


class WorkspaceService:
    """Creates and hands out :class:`UserWorkspace` instances."""

    def __init__(self, workspaces_root: Path) -> None:
        self._workspaces_root = Path(workspaces_root)

    @property
    def workspaces_root(self) -> Path:
        return self._workspaces_root

    def for_user(self, user_id: str) -> UserWorkspace:
        root_directory = self._workspaces_root / user_id
        root_directory.mkdir(parents=True, exist_ok=True)
        return UserWorkspace(user_id=user_id, root_directory=root_directory)

    def delete_for_user(self, user_id: str) -> None:
        root_directory = self._workspaces_root / user_id
        if root_directory.exists():
            shutil.rmtree(root_directory, ignore_errors=True)

    def existing_user_ids(self) -> Iterable[str]:
        if not self._workspaces_root.exists():
            return []
        return (entry.name for entry in self._workspaces_root.iterdir() if entry.is_dir())
