from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path

from app.api import heatmap, dropoff, video
from app.database import engine, Base, close_redis
from app.services.ml_predictor import get_predictor

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Course Portrait Service...")
    
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("DB tables created/verified")
    except Exception as e:
        logger.warning(f"DB initialization error (may be expected): {e}")
    
    try:
        predictor = get_predictor()
        logger.info("ML models loaded")
    except Exception as e:
        logger.warning(f"Failed to load ML models: {e}")
    
    logger.info("Service started successfully")
    
    yield
    
    logger.info("Stopping Course Portrait Service...")
    await close_redis()
    await engine.dispose()
    logger.info("Service stopped")


app = FastAPI(
    title="Course Portrait Service",
    description="Microservice for course difficulty analysis and bottleneck detection",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# /api/v1/courses/{course_id}/heatmap - module difficulty heatmap
app.include_router(heatmap.router, prefix="/api/v1")
# /api/v1/courses/{course_id}/dropoff-points - dropoff points
# /api/v1/courses/{course_id}/funnel - completion funnel
# /api/v1/courses/{course_id}/recommendations - recommendations
app.include_router(dropoff.router, prefix="/api/v1")
# /api/v1/courses/{course_id}/video-analytics - video analytics
app.include_router(video.router, prefix="/api/v1")

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)

if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/dashboard")
async def dashboard():
    dashboard_file = static_dir / "dashboard.html"
    if dashboard_file.exists():
        return FileResponse(dashboard_file)
    return {"message": "Dashboard not found. Please create app/static/dashboard.html"}


@app.get("/")
async def root():
    return {
        "service": "Course Portrait Service",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "dashboard": "/dashboard",
        "endpoints": {
            "heatmap": "/api/v1/courses/{course_id}/heatmap",
            "dropoff": "/api/v1/courses/{course_id}/dropoff-points",
            "funnel": "/api/v1/courses/{course_id}/funnel",
            "recommendations": "/api/v1/courses/{course_id}/recommendations",
            "videoAnalytics": "/api/v1/courses/{course_id}/video-analytics",
            "courseInfo": "/api/v1/courses/{course_id}/info"
        }
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True
    )
