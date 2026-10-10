# SecurePDF

SecurePDF is a production-oriented college project for automated detection and redaction of personally identifiable information (PII) in PDF files.

## Architecture direction

The project is planned as a modular monolith: a FastAPI backend, a React frontend, MySQL with SQLAlchemy and Alembic, and Docker-based local services. Future PDF processing, OCR, PII detection, and background work will use the selected project tools, but none of those features are implemented in this initial foundation.

## Backend setup

From the repository root, create and activate the backend virtual environment:

```powershell
uv venv backend/.venv --python 3.12
.\backend\.venv\Scripts\Activate.ps1
```

Install the current backend dependencies:

```powershell
python -m pip install -r backend/requirements.txt
```

Start the FastAPI development server:

```powershell
python -m uvicorn app.main:app --app-dir backend --reload
```

## Health check

With the server running, open `http://127.0.0.1:8000/health` or run:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

The endpoint returns a JSON response confirming that SecurePDF is running.

## PDF upload (development)

Upload a PDF with an existing development user ID. This temporary `user_id` form field is only for local development until authentication is implemented.

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/documents/upload" `
  -F "user_id=YOUR_EXISTING_USER_ID" `
  -F "file=@C:\path\to\document.pdf;type=application/pdf"
```

PowerShell 7 alternative:

```powershell
$form = @{
  user_id = "YOUR_EXISTING_USER_ID"
  file = Get-Item "C:\path\to\document.pdf"
}
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/documents/upload" -Method Post -Form $form
```

The endpoint validates the PDF signature and readability, limits uploads to 25 MB by default, and returns safe document metadata. It classifies readable PDFs as `digital`, `scanned`, or `mixed` using machine-readable text extracted from each page; it does not perform OCR. Development uploads are saved under `backend/storage/uploads/`. This local filesystem storage is temporary and will be replaced by object storage in a later phase.

Set `MAX_UPLOAD_SIZE_MB` before starting the application to change the local development size limit.

## Database setup

SecurePDF uses MySQL with SQLAlchemy and Alembic. Copy `.env.example` to `.env`, set a local `DATABASE_URL`, and export it before running migrations:

```powershell
$env:DATABASE_URL = "mysql+pymysql://securepdf_user:your_password@localhost:3306/securepdf"
.\backend\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
```

The database layer is limited to the initial schema at this stage; no authentication or document-processing behavior is implemented.

To start the local MySQL development database after Docker Desktop is running:

```powershell
docker compose up -d mysql
docker compose ps
```
