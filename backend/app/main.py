from pathlib import Path

from backend.app.api.routes.applications import router as applications_router
from backend.app.api.routes.executions import router as executions_router
from backend.app.api.routes.feedback import router as feedback_router
from backend.app.api.routes.orchestrator import router as orchestrator_router
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes.jobs import router as jobs_router
from backend.app.api.routes.resumes import router as resumes_router
from backend.app.api.routes.searches import router as searches_router
from backend.app.core.config import settings


STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title=settings.app_name)
app.include_router(resumes_router, prefix="/resumes", tags=["resumes"])
app.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
app.include_router(searches_router, prefix="/searches", tags=["searches"])
app.include_router(applications_router, prefix="/applications", tags=["applications"])
app.include_router(executions_router, prefix="/executions", tags=["executions"])
app.include_router(feedback_router, prefix="/feedback", tags=["feedback"])
app.include_router(orchestrator_router, prefix="/orchestrator", tags=["orchestrator"])
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
