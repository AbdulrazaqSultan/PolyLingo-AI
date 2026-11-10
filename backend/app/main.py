from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from backend.app.core.config import config
from backend.app.core.errors import ServiceError
from backend.app.db.session import initialize, Session
from backend.app.repositories.registry import seed
from backend.app.models.database_models import OperationalLog
from backend.app.api import public, admin
from backend.app.core.admission import InferenceAdmissionMiddleware


@asynccontextmanager
async def lifespan(app):
    initialize()
    with Session() as db:
        seed(db)
    yield


app = FastAPI(
    title="PolyLingo AI",
    version=config.version,
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url="/api/redoc",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
    expose_headers=["X-Synthesis-Ms"],
)
app.include_router(public.router)
app.include_router(admin.router)


@app.get("/docs", include_in_schema=False)
def docs_redirect():
    return RedirectResponse("/api/docs")


@app.get("/redoc", include_in_schema=False)
def redoc_redirect():
    return RedirectResponse("/api/redoc")


@app.get("/openapi.json", include_in_schema=False)
def schema_redirect():
    return RedirectResponse("/api/openapi.json")


@app.middleware("http")
async def protect(request: Request, call_next):
    if (
        request.headers.get("content-length", "").isdigit()
        and int(request.headers["content-length"])
        > (config.max_upload_mb + 1) * 1024 * 1024
    ):
        return JSONResponse(
            status_code=413, content={"detail": "Request is too large."}
        )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


app.state.in_flight = 0
app.add_middleware(InferenceAdmissionMiddleware, state=app.state)


@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    return JSONResponse(
        status_code=422,
        content={"detail": "Invalid input. Check required fields, types, and limits."},
    )


@app.exception_handler(ServiceError)
async def service_error(request, error):
    with Session() as db:
        db.add(
            OperationalLog(
                category="speech" if "/speech/" in request.url.path else "translation",
                message=error.message[:160],
            )
        )
        db.commit()
    return JSONResponse(status_code=error.status, content={"detail": error.message})


@app.exception_handler(Exception)
async def unexpected_error(request, error):
    with Session() as db:
        db.add(
            OperationalLog(
                category="request",
                message="Request failed. Check service configuration and dependencies.",
            )
        )
        db.commit()
    return JSONResponse(
        status_code=500,
        content={
            "detail": "The request could not be completed. Please retry or contact the administrator."
        },
    )
