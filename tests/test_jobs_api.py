
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Document, PIIEntity, ProcessingJob, User
from app.security import create_access_token


client = TestClient(app)


def _create_test_user(session, *, name: str = "Jobs API Test User"):
    """Create a real database user for API tests."""

    user = User(
        name=name,
        email=f"jobs-api-{uuid4()}@example.com",
        password_hash="test-password-hash",
        is_active=True,
    )

    session.add(user)
    session.flush()

    return user


def _create_test_document(session, user):
    """Create a real database document owned by the given user."""

    document = Document(
        user_id=user.id,
        original_filename="jobs-api-test.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        page_count=1,
        document_type="digital",
        status="uploaded",
        original_storage_key=f"uploads/{uuid4()}.pdf",
        redacted_storage_key=None,
        sha256_hash=uuid4().hex + uuid4().hex,
    )

    session.add(document)
    session.commit()
    session.refresh(document)

    return document


def _create_test_candidate(document):
    """Create a real PII candidate for API tests."""

    session = SessionLocal()

    try:
        candidate = PIIEntity(
            document_id=document.id,
            entity_type="EMAIL",
            detected_text="alex@example.com",
            confidence=1.0,
            page_number=1,
            bounding_boxes=[
                {"x0": 10, "y0": 20, "x1": 100, "y1": 35}
            ],
            source="regex",
            review_status="review_required",
            review_decision=None,
        )

        session.add(candidate)
        session.commit()
        session.refresh(candidate)

        return candidate.id

    finally:
        session.close()


def _cleanup(session, user_ids, document_ids):
    """Remove test records from the real database."""

    for document_id in document_ids:
        session.query(PIIEntity).filter(
            PIIEntity.document_id == document_id
        ).delete(synchronize_session=False)

        session.query(ProcessingJob).filter(
            ProcessingJob.document_id == document_id
        ).delete(synchronize_session=False)

    for document_id in document_ids:
        session.query(Document).filter(
            Document.id == document_id
        ).delete(synchronize_session=False)

    for user_id in user_ids:
        session.query(User).filter(
            User.id == user_id
        ).delete(synchronize_session=False)

    session.commit()


def _auth_headers(user_id: str) -> dict[str, str]:
    """Return Bearer authentication headers for a test user."""

    token = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def db_document():
    session = SessionLocal()

    user = None
    document = None

    try:
        user = _create_test_user(session)
        document = _create_test_document(session, user)

        yield user, document

    finally:
        try:
            if user is not None and document is not None:
                _cleanup(
                    session,
                    user_ids=[user.id],
                    document_ids=[document.id],
                )
        finally:
            session.close()


# ---------------------------------------------------------------------
# Processing job creation
# ---------------------------------------------------------------------


def test_create_processing_job(db_document):
    user, document = db_document

    response = client.post(
        f"/api/v1/documents/{document.id}/jobs",
        json={"job_type": "PDF_PROCESSING"},
        headers=_auth_headers(user.id),
    )

    assert response.status_code == 201

    data = response.json()

    assert data["job_id"]
    assert data["document_id"] == document.id
    assert data["job_type"] == "PDF_PROCESSING"
    assert data["status"] == "PENDING"
    assert data["progress"] == 0
    assert data["attempt_count"] == 0
    assert data["error_code"] is None
    assert data["error_message"] is None


def test_create_processing_job_uses_default_job_type(db_document):
    user, document = db_document

    response = client.post(
        f"/api/v1/documents/{document.id}/jobs",
        json={},
        headers=_auth_headers(user.id),
    )

    assert response.status_code == 201

    data = response.json()

    assert data["job_type"] == "PDF_PROCESSING"
    assert data["status"] == "PENDING"


def test_create_processing_job_for_missing_document(db_document):
    user, _ = db_document

    response = client.post(
        f"/api/v1/documents/{uuid4()}/jobs",
        json={"job_type": "PDF_PROCESSING"},
        headers=_auth_headers(user.id),
    )

    assert response.status_code == 404


def test_create_processing_job_rejects_empty_job_type(db_document):
    user, document = db_document

    response = client.post(
        f"/api/v1/documents/{document.id}/jobs",
        json={"job_type": ""},
        headers=_auth_headers(user.id),
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------
# Processing job retrieval and access control
# ---------------------------------------------------------------------


def test_get_processing_job(db_document):
    user, document = db_document

    create_response = client.post(
        f"/api/v1/documents/{document.id}/jobs",
        json={"job_type": "PDF_PROCESSING"},
        headers=_auth_headers(user.id),
    )

    assert create_response.status_code == 201

    created_job = create_response.json()

    response = client.get(
        f"/api/v1/jobs/{created_job['job_id']}",
        headers=_auth_headers(user.id),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["job_id"] == created_job["job_id"]
    assert data["document_id"] == document.id
    assert data["status"] == "PENDING"
    assert data["progress"] == 0
    assert data["attempt_count"] == 0


def test_get_missing_processing_job(db_document):
    user, _ = db_document

    response = client.get(
        f"/api/v1/jobs/{uuid4()}",
        headers=_auth_headers(user.id),
    )

    assert response.status_code == 404


def test_create_processing_job_requires_authentication(db_document):
    _, document = db_document

    response = client.post(
        f"/api/v1/documents/{document.id}/jobs",
        json={"job_type": "PDF_PROCESSING"},
    )

    assert response.status_code == 401


def test_get_processing_job_requires_authentication(db_document):
    user, document = db_document

    create_response = client.post(
        f"/api/v1/documents/{document.id}/jobs",
        json={"job_type": "PDF_PROCESSING"},
        headers=_auth_headers(user.id),
    )

    assert create_response.status_code == 201

    job_id = create_response.json()["job_id"]

    response = client.get(f"/api/v1/jobs/{job_id}")

    assert response.status_code == 401


def test_user_cannot_access_another_users_job(db_document):
    owner, document = db_document

    session = SessionLocal()
    other_user = None

    try:
        other_user = _create_test_user(
            session,
            name="Other Jobs API User",
        )
        session.commit()

        create_response = client.post(
            f"/api/v1/documents/{document.id}/jobs",
            json={"job_type": "PDF_PROCESSING"},
            headers=_auth_headers(owner.id),
        )

        assert create_response.status_code == 201

        job_id = create_response.json()["job_id"]

        response = client.get(
            f"/api/v1/jobs/{job_id}",
            headers=_auth_headers(other_user.id),
        )

        assert response.status_code == 404

    finally:
        try:
            if other_user is not None:
                _cleanup(
                    session,
                    user_ids=[other_user.id],
                    document_ids=[],
                )
        finally:
            session.close()


def test_user_cannot_create_job_for_another_users_document(db_document):
    _, document = db_document

    session = SessionLocal()
    other_user = None

    try:
        other_user = _create_test_user(
            session,
            name="Other Jobs API User",
        )
        session.commit()

        response = client.post(
            f"/api/v1/documents/{document.id}/jobs",
            json={"job_type": "PDF_PROCESSING"},
            headers=_auth_headers(other_user.id),
        )

        assert response.status_code == 404

    finally:
        try:
            if other_user is not None:
                _cleanup(
                    session,
                    user_ids=[other_user.id],
                    document_ids=[],
                )
        finally:
            session.close()


# ---------------------------------------------------------------------
# PII review API
# ---------------------------------------------------------------------


def test_review_candidate_redact_decision(db_document):
    user, document = db_document
    candidate_id = _create_test_candidate(document)

    response = client.post(
        f"/api/v1/documents/{document.id}/pii-entities/"
        f"{candidate_id}/decision",
        json={"decision": "REDACT"},
        headers=_auth_headers(user.id),
    )

    assert response.status_code == 200

    session = SessionLocal()

    try:
        candidate = session.query(PIIEntity).filter(
            PIIEntity.id == candidate_id
        ).one()

        assert candidate.review_decision == "REDACT"
        assert candidate.review_status == "approved_for_redaction"

    finally:
        session.close()


def test_review_candidate_keep_decision(db_document):
    user, document = db_document
    candidate_id = _create_test_candidate(document)

    response = client.post(
        f"/api/v1/documents/{document.id}/pii-entities/"
        f"{candidate_id}/decision",
        json={"decision": "KEEP"},
        headers=_auth_headers(user.id),
    )

    assert response.status_code == 200

    session = SessionLocal()

    try:
        candidate = session.query(PIIEntity).filter(
            PIIEntity.id == candidate_id
        ).one()

        assert candidate.review_decision == "KEEP"
        assert candidate.review_status == "kept"

    finally:
        session.close()


def test_review_candidate_rejects_invalid_decision(db_document):
    user, document = db_document
    candidate_id = _create_test_candidate(document)

    response = client.post(
        f"/api/v1/documents/{document.id}/pii-entities/"
        f"{candidate_id}/decision",
        json={"decision": "IGNORE"},
        headers=_auth_headers(user.id),
    )

    assert response.status_code == 422


def test_review_candidate_rejects_missing_candidate(db_document):
    user, document = db_document

    response = client.post(
        f"/api/v1/documents/{document.id}/pii-entities/"
        f"{uuid4()}/decision",
        json={"decision": "REDACT"},
        headers=_auth_headers(user.id),
    )

    assert response.status_code == 404


def test_review_candidate_rejects_another_users_document(db_document):
    _, document = db_document
    candidate_id = _create_test_candidate(document)

    session = SessionLocal()
    other_user = None

    try:
        other_user = _create_test_user(
            session,
            name="Other PII Review User",
        )
        session.commit()

        response = client.post(
            f"/api/v1/documents/{document.id}/pii-entities/"
            f"{candidate_id}/decision",
            json={"decision": "REDACT"},
            headers=_auth_headers(other_user.id),
        )

        assert response.status_code == 404

    finally:
        try:
            if other_user is not None:
                _cleanup(
                    session,
                    user_ids=[other_user.id],
                    document_ids=[],
                )
        finally:
            session.close()


def test_review_candidate_requires_authentication(db_document):
    _, document = db_document
    candidate_id = _create_test_candidate(document)

    response = client.post(
        f"/api/v1/documents/{document.id}/pii-entities/"
        f"{candidate_id}/decision",
        json={"decision": "REDACT"},
    )

    assert response.status_code == 401


def test_job_response_includes_candidate_review_decision(db_document):
    user, document = db_document

    create_response = client.post(
        f"/api/v1/documents/{document.id}/jobs",
        json={"job_type": "PDF_PROCESSING"},
        headers=_auth_headers(user.id),
    )

    assert create_response.status_code == 201

    job_id = create_response.json()["job_id"]
    candidate_id = _create_test_candidate(document)

    review_response = client.post(
        f"/api/v1/documents/{document.id}/pii-entities/"
        f"{candidate_id}/decision",
        json={"decision": "REDACT"},
        headers=_auth_headers(user.id),
    )

    assert review_response.status_code == 200

    job_response = client.get(
        f"/api/v1/jobs/{job_id}",
        headers=_auth_headers(user.id),
    )

    assert job_response.status_code == 200

    candidates = job_response.json()["pii_entities"]

    candidate = next(
        item
        for item in candidates
        if str(item["id"]) == str(candidate_id)
    )

    assert candidate["review_decision"] == "REDACT"
    assert candidate["review_status"] == "approved_for_redaction"
