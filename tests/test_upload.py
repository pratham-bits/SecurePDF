"""Tests for the authenticated PDF upload endpoint."""

import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

import pymupdf
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine, get_db
from app.main import app
from app.models import User, Document
from app.security import create_access_token


ONE_PIXEL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\x0dIDAT\x08\xd7c\xf8\xcf\xc0\xf0\x1f"
    b"\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00"
    b"IEND\xaeB`\x82"
)


class UploadEndpointTests(unittest.TestCase):
    """Tests for the authenticated PDF upload endpoint."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()

        cls.database_url = (
            f"sqlite:///{Path(cls.temp_dir.name) / 'test.db'}"
        )

        cls.storage_dir = (
            Path(cls.temp_dir.name) / "storage"
        )

        # ------------------------------------------------------------------
        # Configure the application for isolated testing.
        # ------------------------------------------------------------------

        os.environ["STORAGE_DIR"] = str(cls.storage_dir)

        # ------------------------------------------------------------------
        # Create the test database.
        #
        # NOTE:
        # The production application normally uses MySQL. For these tests,
        # we create a separate SQLite database so tests never touch the
        # development database.
        # ------------------------------------------------------------------

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        cls.test_engine = create_engine(
            cls.database_url,
            connect_args={"check_same_thread": False},
        )

        cls.TestSessionLocal = sessionmaker(
            bind=cls.test_engine,
            autoflush=False,
            autocommit=False,
        )

        Base.metadata.create_all(
            cls.test_engine
        )

        # ------------------------------------------------------------------
        # Override FastAPI's database dependency.
        # ------------------------------------------------------------------

        def override_get_db():
            session = cls.TestSessionLocal()

            try:
                yield session
            finally:
                session.close()

        cls.override_get_db = override_get_db

        app.dependency_overrides[get_db] = (
            cls.override_get_db
        )

        # ------------------------------------------------------------------
        # Create the authenticated test user.
        # ------------------------------------------------------------------

        session = cls.TestSessionLocal()

        try:
            cls.user = User(
                name="Development Test User",
                email="upload-test@example.test",
                password_hash="not-used-in-tests",
                is_active=True,
            )

            session.add(cls.user)
            session.commit()
            session.refresh(cls.user)

            cls.user_id = cls.user.id

        finally:
            session.close()

        # ------------------------------------------------------------------
        # Create JWT for authenticated upload tests.
        # ------------------------------------------------------------------

        cls.access_token = create_access_token(
            cls.user_id
        )

        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        # Remove FastAPI dependency override.
        app.dependency_overrides.clear()

        # Dispose test database.
        cls.test_engine.dispose()

        # Remove temporary test directory and storage.
        cls.temp_dir.cleanup()

    def upload(
        self,
        content: bytes,
        filename: str = "sample.pdf",
        token: str | None = None,
        data: dict[str, str] | None = None,
    ):
        """Upload a PDF using the supplied JWT token."""

        headers = {}

        if token is None:
            token = self.access_token

        headers["Authorization"] = (
            f"Bearer {token}"
        )

        return self.client.post(
            "/api/v1/documents/upload",
            headers=headers,
            data=data,
            files={
                "file": (
                    filename,
                    BytesIO(content),
                    "application/pdf",
                )
            },
        )

    @staticmethod
    def pdf_content(
        page_types: list[str],
    ) -> bytes:
        """Generate a small PDF for upload/classification tests."""

        pdf = pymupdf.open()

        for page_type in page_types:
            page = pdf.new_page()

            if page_type == "text":
                page.insert_text(
                    (72, 72),
                    "Meaningful machine-readable text",
                )

            elif page_type == "image":
                page.insert_image(
                    page.rect,
                    stream=ONE_PIXEL_PNG,
                )

            elif page_type == "whitespace":
                page.insert_text(
                    (72, 72),
                    "   \t   ",
                )

            elif page_type == "empty":
                pass

            else:
                pdf.close()

                raise ValueError(
                    f"Unsupported page type: {page_type}"
                )

        content = pdf.tobytes()
        pdf.close()

        return content

    @staticmethod
    def stored_pdf_count() -> int:
        """Return the number of uploaded PDF files in test storage."""

        from app.storage import LocalStorage

        storage = LocalStorage(
            str(
                Path(
                    os.environ["STORAGE_DIR"]
                )
            )
        )

        storage_root = storage.get_path(
            "uploads"
        )

        if not storage_root.exists():
            return 0

        return len(
            list(
                storage_root.glob("*.pdf")
            )
        )

    # ------------------------------------------------------------------
    # Authentication tests
    # ------------------------------------------------------------------

    def test_upload_requires_authentication(
        self,
    ) -> None:
        """Unauthenticated upload requests must be rejected."""

        response = self.upload(
            self.pdf_content(["text"]),
            "unauthenticated.pdf",
            token="",
        )

        self.assertEqual(
            response.status_code,
            401,
        )

    def test_upload_rejects_invalid_token(
        self,
    ) -> None:
        """Upload requests with an invalid JWT must be rejected."""

        response = self.upload(
            self.pdf_content(["text"]),
            "invalid-token.pdf",
            token="invalid.token.value",
        )

        self.assertEqual(
            response.status_code,
            401,
        )

    def test_upload_uses_authenticated_user(
        self,
    ) -> None:
        """
        The document owner must come from the authenticated JWT,
        not from a client-supplied user_id form field.
        """

        response = self.upload(
            self.pdf_content(["text"]),
            "authenticated-owner.pdf",
            data={
                "user_id": "some-other-user-id",
            },
        )

        self.assertEqual(
            response.status_code,
            201,
        )

        document_id = response.json()[
            "document_id"
        ]

        session = self.TestSessionLocal()

        try:
            document = session.get(
                Document,
                document_id,
            )

            self.assertIsNotNone(
                document
            )

            self.assertEqual(
                document.user_id,
                self.user_id,
            )

        finally:
            session.close()

    # ------------------------------------------------------------------
    # PDF upload and classification tests
    # ------------------------------------------------------------------

    def test_digital_pdf_upload_creates_document_record(
        self,
    ) -> None:
        """A digital PDF should upload successfully and create a record."""

        content = self.pdf_content(
            ["text"]
        )

        response = self.upload(
            content
        )

        self.assertEqual(
            response.status_code,
            201,
        )

        payload = response.json()

        self.assertEqual(
            payload["filename"],
            "sample.pdf",
        )

        self.assertEqual(
            payload["page_count"],
            1,
        )

        self.assertEqual(
            payload["document_type"],
            "digital",
        )

        self.assertEqual(
            payload["status"],
            "uploaded",
        )

        session = self.TestSessionLocal()

        try:
            document = session.get(
                Document,
                payload["document_id"],
            )

            self.assertIsNotNone(
                document
            )

            self.assertEqual(
                document.user_id,
                self.user_id,
            )

            self.assertEqual(
                document.size_bytes,
                len(content),
            )

            self.assertEqual(
                document.document_type,
                "digital",
            )

            self.assertEqual(
                document.original_storage_key,
                (
                    f"uploads/"
                    f"{payload['document_id']}.pdf"
                ),
            )

            from app.documents import storage

            self.assertTrue(
                storage.exists(
                    document.original_storage_key
                )
            )

        finally:
            session.close()

    def test_image_only_pdf_is_classified_as_scanned(
        self,
    ) -> None:
        """An image-only PDF should be classified as scanned."""

        response = self.upload(
            self.pdf_content(["image"]),
            "image-only.pdf",
        )

        self.assertEqual(
            response.status_code,
            201,
        )

        self.assertEqual(
            response.json()["document_type"],
            "scanned",
        )

    def test_mixed_pdf_is_classified_as_mixed(
        self,
    ) -> None:
        """A PDF containing text and image pages should be mixed."""

        response = self.upload(
            self.pdf_content(
                ["text", "image"]
            ),
            "mixed.pdf",
        )

        self.assertEqual(
            response.status_code,
            201,
        )

        self.assertEqual(
            response.json()["page_count"],
            2,
        )

        self.assertEqual(
            response.json()["document_type"],
            "mixed",
        )

    def test_empty_page_is_classified_as_scanned(
        self,
    ) -> None:
        """An empty page should be treated as scanned/non-text."""

        response = self.upload(
            self.pdf_content(["empty"]),
            "empty.pdf",
        )

        self.assertEqual(
            response.status_code,
            201,
        )

        self.assertEqual(
            response.json()["document_type"],
            "scanned",
        )

    def test_whitespace_only_page_is_classified_as_scanned(
        self,
    ) -> None:
        """A whitespace-only page should be treated as scanned."""

        response = self.upload(
            self.pdf_content(["whitespace"]),
            "whitespace.pdf",
        )

        self.assertEqual(
            response.status_code,
            201,
        )

        self.assertEqual(
            response.json()["document_type"],
            "scanned",
        )

    # ------------------------------------------------------------------
    # Upload validation tests
    # ------------------------------------------------------------------

    def test_non_pdf_upload_is_rejected(
        self,
    ) -> None:
        """A file without valid PDF content must be rejected."""

        before_count = (
            self.stored_pdf_count()
        )

        response = self.upload(
            b"This is not a PDF.",
            "renamed.pdf",
        )

        self.assertEqual(
            response.status_code,
            415,
        )

        self.assertEqual(
            self.stored_pdf_count(),
            before_count,
        )

    def test_corrupted_pdf_upload_is_rejected(
        self,
    ) -> None:
        """A corrupted/incomplete PDF must be rejected."""

        before_count = (
            self.stored_pdf_count()
        )

        response = self.upload(
            b"%PDF-1.7\nThis is not a complete PDF",
            "broken.pdf",
        )

        self.assertEqual(
            response.status_code,
            422,
        )

        self.assertEqual(
            self.stored_pdf_count(),
            before_count,
        )


if __name__ == "__main__":
    unittest.main()