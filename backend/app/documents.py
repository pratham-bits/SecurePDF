"""PDF upload, validation, and secure redacted-document download endpoints."""

import hashlib
import os
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import pymupdf
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.artifact_service import (
    ArtifactServiceError,
    DocumentArtifactService,
)
from app.classification import classify_pdf
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Document, User
from app.storage import LocalStorage, StorageError


router = APIRouter(
    prefix="/api/v1/documents",
    tags=["documents"],
)


BACKEND_DIR = Path(__file__).resolve().parents[1]

STORAGE_DIR = Path(
    os.getenv(
        "STORAGE_DIR",
        BACKEND_DIR / "storage",
    )
).resolve()

MAX_UPLOAD_SIZE_MB = int(
    os.getenv("MAX_UPLOAD_SIZE_MB", "25")
)

MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
CHUNK_SIZE = 1024 * 1024

storage = LocalStorage(STORAGE_DIR)


def validate_pdf(storage_path: Path) -> int:
    """Open a PDF with PyMuPDF and return its page count."""

    pdf = None

    try:
        pdf = pymupdf.open(
            stream=storage_path.read_bytes(),
            filetype="pdf",
        )

        if not pdf.is_pdf:
            raise ValueError("Not a PDF")

        if pdf.page_count < 1:
            raise ValueError("PDF has no readable pages")

        return pdf.page_count

    except (
        pymupdf.FileDataError,
        RuntimeError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The uploaded PDF is corrupt or cannot be read.",
        ) from exc

    finally:
        if pdf is not None:
            pdf.close()


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
    file: Annotated[
        UploadFile,
        File(...),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> dict[str, str | int]:
    """Validate, store, and register a PDF for the authenticated user."""

    safe_filename = Path(file.filename or "upload.pdf").name
    document_id = str(uuid4())
    storage_key = f"uploads/{document_id}.pdf"
    storage_path: Path | None = None

    try:
        digest = hashlib.sha256()
        size_bytes = 0

        try:
            destination = storage.create(storage_key)
        except StorageError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to store the uploaded document.",
            ) from exc

        try:
            with destination:
                while chunk := await file.read(CHUNK_SIZE):
                    if size_bytes == 0 and not chunk.startswith(b"%PDF-"):
                        raise HTTPException(
                            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail="The uploaded file is not a PDF.",
                        )

                    size_bytes += len(chunk)

                    if size_bytes > MAX_UPLOAD_SIZE_BYTES:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=(
                                f"PDF uploads are limited to "
                                f"{MAX_UPLOAD_SIZE_MB} MB."
                            ),
                        )

                    digest.update(chunk)
                    destination.write(chunk)

        except HTTPException:
            storage.delete(storage_key)
            raise

        except OSError as exc:
            storage.delete(storage_key)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to store the uploaded document.",
            ) from exc

        if size_bytes == 0:
            storage.delete(storage_key)
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="The uploaded file is not a PDF.",
            )

        storage_path = storage.get_path(storage_key)
        page_count = validate_pdf(storage_path)

        try:
            document_type = classify_pdf(storage_path)
        except ValueError as exc:
            storage.delete(storage_key)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="The uploaded PDF could not be classified.",
            ) from exc

        document = Document(
            id=document_id,
            user_id=current_user.id,
            original_filename=safe_filename,
            mime_type="application/pdf",
            size_bytes=size_bytes,
            page_count=page_count,
            document_type=document_type,
            status="uploaded",
            original_storage_key=storage_key,
            sha256_hash=digest.hexdigest(),
        )

        db.add(document)
        db.commit()
        db.refresh(document)

        return {
            "document_id": document.id,
            "filename": document.original_filename,
            "size_bytes": document.size_bytes,
            "page_count": document.page_count or 0,
            "document_type": document.document_type or "",
            "status": document.status,
            "sha256_hash": document.sha256_hash,
        }

    except HTTPException:
        # Upload validation errors are cleaned up before storage_path
        # is assigned; this handles later validation errors.
        if storage_path is not None:
            storage.delete(storage_key)
        raise

    except SQLAlchemyError as exc:
        db.rollback()

        if storage_path is not None:
            storage.delete(storage_key)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save the document record.",
        ) from exc

    finally:
        await file.close()


@router.get(
    "/{document_id}/download",
    response_class=FileResponse,
    status_code=status.HTTP_200_OK,
)
def download_redacted_document(
    document_id: str,
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> FileResponse:
    """Download the finalized PDF belonging to the authenticated user."""

    document = db.get(Document, document_id)

    # Return the same response for missing and non-owned documents
    # so this endpoint does not disclose other users' document IDs.
    if document is None or document.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    # A storage key alone is not proof that finalization succeeded.
    if not document.redacted_storage_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The redacted PDF is not available yet. Finalize redaction first.",
        )

    artifact_service = DocumentArtifactService(storage)

    try:
        redacted_path = artifact_service.get_redacted_path(document.id)
    except ArtifactServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The finalized PDF could not be found in storage.",
        ) from exc

    # Ensure the artifact service resolves the same key recorded on
    # the document, rather than serving a different generated artifact.
    try:
        expected_path = storage.get_path(document.redacted_storage_key)
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The finalized PDF could not be found in storage.",
        ) from exc

    if (
        redacted_path.resolve() != expected_path.resolve()
        or not expected_path.is_file()
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The finalized PDF could not be found in storage.",
        )

    original_name = Path(
        document.original_filename or "document.pdf"
    ).name

    filename_stem = Path(original_name).stem or "document"
    download_filename = f"{filename_stem}_redacted.pdf"

    return FileResponse(
        path=redacted_path,
        media_type="application/pdf",
        filename=download_filename,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
