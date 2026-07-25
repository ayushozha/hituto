"""Deep Agent storage backends for the web process (course-authoring-flow §2).

The web process must never mount a writable real-filesystem backend — a subagent
`write_file` could otherwise write inside the repo. Skills are mounted read-only
under `/skills/`; all scratch handoff files live in the ephemeral StateBackend.
"""
from __future__ import annotations

from pathlib import Path

_SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"

_DENIED = "read-only skills mount: writes are not permitted in the web process"


def readonly_skills_backend():
    """FilesystemBackend over coursegen/skills with every write path disabled."""
    from deepagents.backends import FilesystemBackend
    from deepagents.backends.protocol import EditResult, FileUploadResponse, WriteResult

    class _ReadOnlyFilesystemBackend(FilesystemBackend):
        def write(self, file_path: str, content: str) -> WriteResult:  # type: ignore[override]
            return WriteResult(error=_DENIED, path=None)

        async def awrite(self, file_path: str, content: str) -> WriteResult:  # type: ignore[override]
            return WriteResult(error=_DENIED, path=None)

        def edit(  # type: ignore[override]
            self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
        ) -> EditResult:
            return EditResult(error=_DENIED, path=None, occurrences=None)

        async def aedit(  # type: ignore[override]
            self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
        ) -> EditResult:
            return EditResult(error=_DENIED, path=None, occurrences=None)

        def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:  # type: ignore[override]
            return [FileUploadResponse(path=p, error="permission_denied") for p, _ in files]

        async def aupload_files(  # type: ignore[override]
            self, files: list[tuple[str, bytes]]
        ) -> list[FileUploadResponse]:
            return [FileUploadResponse(path=p, error="permission_denied") for p, _ in files]

    return _ReadOnlyFilesystemBackend(root_dir=str(_SKILLS_DIR), virtual_mode=True)


def web_backend():
    """Composite backend for web-process Deep Agents.

    Scratch files (`/build/*`, todos, drafts) go to the ephemeral StateBackend;
    `/skills/…` reads resolve inside coursegen/skills and can never be written.
    """
    from deepagents.backends import CompositeBackend, StateBackend

    return CompositeBackend(default=StateBackend(), routes={"/skills/": readonly_skills_backend()})
