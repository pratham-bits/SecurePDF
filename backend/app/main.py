
"""FastAPI entry point for SecurePDF."""

from fastapi import FastAPI  # type: ignore[reportMissingImports]
from fastapi.middleware.cors import CORSMiddleware

from app.auth import router as auth_router
from app.documents import router as documents_router
from app.jobs import router as jobs_router


app = FastAPI(title="SecurePDF")

# Allow the local React/Vite frontend during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(documents_router)
app.include_router(jobs_router)
app.include_router(auth_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Return the service health status."""

    return {
        "status": "ok",
        "message": "SecurePDF is running",
    }
