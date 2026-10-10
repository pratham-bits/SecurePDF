# SecurePDF

**A backend-focused PDF PII detection and redaction platform** built with FastAPI, GLiNER, rule-based detection, PyMuPDF, Celery, and MySQL/SQLAlchemy.

SecurePDF is a document-processing application designed to identify potentially sensitive personally identifiable information (PII) in PDF files, let users review detection candidates, and produce redacted PDF artifacts.

> **Project status:** Active development. SecurePDF is a portfolio and engineering project, not a certified or production-ready data-loss-prevention solution. Detection quality, redaction correctness, authentication behavior, and deployment security must be validated for the intended environment before use with real confidential documents.

## Why SecurePDF?

PDFs often contain sensitive information in text, forms, and scanned pages. Manually finding and removing that information can be slow and error-prone. SecurePDF explores a modular backend workflow for extracting PDF content, identifying PII candidates, reviewing decisions, and generating a redacted output document.

The project emphasizes backend engineering concerns:

- REST API design and request validation with FastAPI
- Authentication and protected endpoints
- PDF classification, extraction, and coordinate-aware processing
- PII candidate detection using contextual and deterministic approaches
- Review decisions and controlled finalization
- Relational persistence and database migrations
- Background processing with Celery
- Artifact storage and focused automated tests

## Core workflow

1. **Authenticate** — obtain an access token and call protected API endpoints.
2. **Upload a PDF** — validate the uploaded file and register the document.
3. **Classify and extract** — determine the document's text characteristics and extract machine-readable text while preserving page boundaries.
4. **Detect PII candidates** — use the configured detection pipeline, including rule-based matching and GLiNER-based entity recognition where enabled.
5. **Review candidates** — accept or reject candidate redactions through review decisions.
6. **Finalize processing** — apply approved redactions and store the resulting artifact.
7. **Retrieve job status** — inspect processing state and the finalization result.

The precise behavior depends on the configured processing path and document type. Scanned and mixed-content PDFs require particular care because OCR quality and mapping detected text back to page coordinates affect redaction accuracy.

## Technology stack

| Area | Technologies | Purpose |
|---|---|---|
| Backend API | Python, FastAPI | REST endpoints, validation, and application services |
| PII detection | GLiNER, rule-based matching | Contextual entity recognition and deterministic pattern detection |
| PDF processing | PyMuPDF | PDF inspection, text extraction, coordinate handling, and redaction |
| OCR | OCR processing modules | Text recognition for scanned or image-based content |
| Database | MySQL, SQLAlchemy | Persistent application and processing data |
| Schema migrations | Alembic | Versioned database schema changes |
| Background jobs | Celery, Redis-compatible broker/backend | Asynchronous processing and task execution |
| Frontend | React, TypeScript, Vite | User interface for interacting with the backend |
| Testing | pytest | Unit, API, processing, and integration-oriented tests |
| Local services | Docker Compose | Local development service setup |

## Architecture

SecurePDF is organized as a modular monolith: application capabilities are separated into modules while remaining within one backend codebase.

```text
React + TypeScript frontend
          |
          | HTTP / JSON + access token
          v
       FastAPI API
          |
          +---- Authentication and authorization
          |
          +---- Document upload and validation
          |
          +---- PDF classification and extraction
          |
          +---- PII detection and review decisions
          |
          +---- Job orchestration and finalization
          |
          +---- SQLAlchemy ---- MySQL
          |
          +---- Celery workers ---- Redis-compatible broker
          |
          +---- Artifact storage
```

### Backend module map

The main backend implementation is under `backend/app/`:

- `main.py` — FastAPI application entry point
- `auth.py`, `security.py`, `dependencies.py` — authentication and request security
- `documents.py` — document upload and document-related endpoints
- `classification.py`, `extraction.py`, `text_pipeline.py` — PDF classification and text extraction
- `pii_rules.py`, `pii_gliner.py`, `pii_pipeline.py`, `redaction_policy.py` — PII detection and policy-related logic
- `review.py`, `pii_review_service.py`, `review_decision.py` — candidate review and decision handling
- `jobs.py`, `job_service.py`, `job_processor.py`, `celery_app.py`, `celery_tasks.py` — job processing and background task integration
- `pii_finalization_service.py`, `final_processing.py`, `final_redaction.py`, `redaction.py` — finalization and redaction-related logic
- `artifact_storage.py`, `artifact_service.py`, `storage.py` — storage abstractions and artifact handling
- `models.py`, `database.py` — ORM models and database configuration
- `alembic/` — database migration configuration and revisions

The module list describes code organization; it does not imply that every processing path is production-hardened.

## API overview

The backend exposes versioned API routes. The following endpoints are implemented in the current development code:

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/auth/register` | Register a user |
| `POST` | `/api/v1/auth/login` | Authenticate and obtain a token |
| `POST` | `/api/v1/auth/token` | Token endpoint |
| `GET` | `/api/v1/auth/me` | Get the authenticated user |
| `POST` | `/api/v1/documents/upload` | Upload a PDF |
| `POST` | `/api/v1/documents/{document_id}/jobs` | Create a processing job |
| `GET` | `/api/v1/jobs/{job_id}` | Get processing job status |
| `POST` | `/api/v1/documents/{document_id}/pii-entities/{candidate_id}/decision` | Save a PII review decision |
| `POST` | `/api/v1/documents/{document_id}/jobs/{job_id}/finalize` | Finalize a reviewed job |

Interactive API documentation is available at `http://127.0.0.1:8000/docs` while the backend is running. Confirm request schemas and authentication requirements there, because API contracts can evolve during development.

## Local development setup

### Prerequisites

Install the following tools:

- Python 3.12
- Node.js and npm compatible with the frontend toolchain
- Docker Desktop with Docker Compose
- Git
- A local MySQL service (or the MySQL service defined in `docker-compose.yml`)
- A Redis-compatible service if running Celery tasks

### 1. Clone the repository

```bash
git clone https://github.com/https://github.com/pratham-bits/SecurePDF/SecurePDF.git
cd SecurePDF
```

Replace `<YOUR_GITHUB_USERNAME>` with the repository owner's GitHub username.

### 2. Configure environment variables

Copy the example environment file:

```powershell
Copy-Item .env.example .env
```

Open `.env` and replace all placeholder passwords and the JWT signing secret with strong, local development values. Ensure the database URL uses the same MySQL username and password as the database configuration.

Never commit `.env`, access tokens, real credentials, private keys, or confidential PDFs. The repository includes `.gitignore` rules intended to exclude local environment files, PDFs, and local storage artifacts.

### 3. Start local services

From the repository root:

```powershell
docker compose up -d
```

Review `docker-compose.yml` to see which services this command starts. If the Redis-compatible broker is not included in the Compose configuration, start or configure it separately before running Celery tasks.

### 4. Set up the Python environment

From the repository root in PowerShell:

```powershell
py -3.12 -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install --upgrade pip
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

For development dependencies and test tooling:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
```

If the virtual environment already exists, reuse it rather than recreating it.

### 5. Apply database migrations

From the repository root:

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m alembic upgrade head
Set-Location ..
```

Ensure the database is reachable and the `DATABASE_URL` in `.env` is correct before applying migrations.

### 6. Start the backend

From the repository root:

```powershell
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

Verify the health endpoint:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Open the API documentation at `http://127.0.0.1:8000/docs`.

### 7. Start the frontend

Open a second terminal:

```powershell
Set-Location .\frontend
npm install
npm run dev
```

The frontend's local API base URL is configured using `VITE_API_BASE_URL`. For local development, it should point to the backend, for example:

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Use a local `frontend/.env` file for this setting; do not commit local `.env` files.

### 8. Run a Celery worker

If the broker/backend are running and configured, open another terminal:

```powershell
Set-Location .\backend
.\.venv\Scripts\python.exe -m celery -A app.celery_app worker --loglevel=INFO --pool=solo
```

The `solo` pool is convenient for local development on Windows. Worker startup alone does not prove that every asynchronous workflow is working; verify task execution with the relevant tests and application flow.

## Testing

Run focused tests while developing:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest .\tests\test_auth.py -q
.\backend\.venv\Scripts\python.exe -m pytest .\tests\test_extraction.py -q
.\backend\.venv\Scripts\python.exe -m pytest .\tests\test_redaction.py -q
```

Run the full test suite when appropriate:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest .\tests -q
```

The test suite covers areas including authentication, document processing, extraction, OCR-related processing, coordinate mapping, redaction geometry, job state, artifact storage, and finalization. Passing tests are useful evidence, but they do not guarantee detection recall, safe redaction, or production readiness for all PDF formats.

## Security and privacy considerations

SecurePDF is designed around sensitive document handling, so security validation is part of the engineering work.

- Keep secrets in environment variables and out of source control.
- Use authentication for protected API operations.
- Validate uploaded files and handle malformed PDFs safely.
- Treat detected PII as candidates that may require human review.
- Verify that redaction removes sensitive content from the actual PDF, rather than only drawing a visual overlay.
- Test text, image, and mixed-content PDFs; inspect output artifacts for residual sensitive information.
- Restrict access to originals, generated artifacts, logs, and temporary files.
- Before deployment, configure HTTPS, secure secret management, request limits, upload-size limits, retention/deletion policies, and production logging.
- Do not use this development project as the sole protection for regulated or highly confidential data.

## Current limitations and roadmap

This project is under active development. Priorities include:

- Validate and improve PII detection quality across diverse real-world documents.
- Test OCR and coordinate mapping on scanned and mixed-content PDFs.
- Ensure policy outcomes consistently determine which candidates require manual review.
- Validate authentication and authorization across all protected routes.
- Complete and test secure redacted-artifact download behavior.
- Improve integration tests for asynchronous jobs, retries, failures, and cleanup.
- Add deployment configuration, operational monitoring, and security hardening.
- Document measured evaluation results and known false-positive/false-negative cases.

## Contributing

This is an evolving engineering project. Bug reports, reproducible test cases, and suggestions for improving detection quality, PDF processing, security, and API design are welcome. Do not submit real personal information or confidential documents in issues or pull requests.

## License

No license has been specified yet. Unless a license is added to the repository, the code should not be assumed to be available for unrestricted reuse.

## Author

Built as a backend-focused software engineering project exploring secure document processing, API design, PII detection, asynchronous work, and PDF redaction.
