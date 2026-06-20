import os
import shutil
import subprocess
import threading
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.database import engine, Base
from app.config import settings
from app.routers import auth, jam, debate, interview, coach, document_analyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("jam_analyzer")
logger.setLevel(logging.INFO)

# Dynamically handle table renames before metadata.create_all
try:
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    with engine.begin() as conn:
        if 'document_sessions' in existing_tables and 'document_video_sessions' not in existing_tables:
            logger.info("Database migration: renaming document_sessions to document_video_sessions")
            conn.execute(text("ALTER TABLE document_sessions RENAME TO document_video_sessions"))
        if 'document_reports' in existing_tables and 'document_communication_reports' not in existing_tables:
            logger.info("Database migration: renaming document_reports to document_communication_reports")
            conn.execute(text("ALTER TABLE document_reports RENAME TO document_communication_reports"))
except Exception as rename_exc:
    logger.warning(f"Failed to check/run table renaming migrations: {rename_exc}")

# Create database tables automatically
Base.metadata.create_all(bind=engine)

# Dynamically ensure all columns exist
try:
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    columns = [c['name'] for c in inspector.get_columns('sessions')]
    with engine.begin() as conn:
        if 'instant_start' not in columns:
            logger.info("Database migration: adding instant_start to sessions table")
            conn.execute(text("ALTER TABLE sessions ADD COLUMN instant_start BOOLEAN DEFAULT 0"))
        if 'preparation_mode' not in columns:
            logger.info("Database migration: adding preparation_mode to sessions table")
            conn.execute(text("ALTER TABLE sessions ADD COLUMN preparation_mode BOOLEAN DEFAULT 0"))
        if 'skip_preparation' not in columns:
            logger.info("Database migration: adding skip_preparation to sessions table")
            conn.execute(text("ALTER TABLE sessions ADD COLUMN skip_preparation BOOLEAN DEFAULT 0"))
        if 'final_score' not in columns:
            logger.info("Database migration: adding final_score to sessions table")
            conn.execute(text("ALTER TABLE sessions ADD COLUMN final_score INTEGER DEFAULT 0"))
        if 'difficulty' not in columns:
            logger.info("Database migration: adding difficulty to sessions table")
            conn.execute(text("ALTER TABLE sessions ADD COLUMN difficulty VARCHAR(50) DEFAULT 'Medium'"))
        if 'session_metadata' not in columns:
            logger.info("Database migration: adding session_metadata to sessions table")
            conn.execute(text("ALTER TABLE sessions ADD COLUMN session_metadata TEXT DEFAULT NULL"))
            
        # Dynamic columns check for communication_dna
        dna_cols = [c['name'] for c in inspector.get_columns('communication_dna')]
        for new_col in [
            'subject_expertise', 'technical_communication', 'explanation_skill', 
            'knowledge_retention', 'teaching_ability', 'technical_communication_skill',
            'presentation_skill', 'subject_knowledge', 'explanation_ability', 'communication_confidence'
        ]:
            if new_col not in dna_cols:
                logger.info(f"Database migration: adding {new_col} to communication_dna table")
                conn.execute(text(f"ALTER TABLE communication_dna ADD COLUMN {new_col} INTEGER DEFAULT 0"))

        # Dynamic columns check for documents
        doc_cols = [c['name'] for c in inspector.get_columns('documents')]
        if 'learning_objectives' not in doc_cols:
            logger.info("Database migration: adding learning_objectives to documents table")
            conn.execute(text("ALTER TABLE documents ADD COLUMN learning_objectives TEXT DEFAULT NULL"))
except Exception as exc:
    logger.warning(f"Failed to check/run DB schema migrations: {exc}")

app = FastAPI(
    title="AI Human Communication Twin Platform API",
    description="Backend services for the AI Human Communication Twin Platform.",
    version="1.0.0"
)

# Configure CORS for Frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.2.22:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure upload dir exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

# Mount upload directory as static files to allow direct streaming/playback in UI
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")


@app.on_event("startup")
async def warmup_models():
    """
    Pre-loads the Faster-Whisper large-v3 model in a background thread so the
    first recording upload does not incur a cold-start penalty.
    """
    def _load_whisper():
        try:
            from app.services.audio_processor import get_whisper_model
            logger.info("[Startup] Pre-loading Faster-Whisper model...")
            get_whisper_model()
            logger.info("[Startup] Faster-Whisper model ready.")
        except Exception as exc:
            logger.warning(f"[Startup] Whisper warm-up failed (will retry on first request): {exc}")

    threading.Thread(target=_load_whisper, daemon=True).start()


# Register Routers
app.include_router(auth.router, prefix="/api")
app.include_router(jam.router, prefix="/api")
app.include_router(jam.api_router, prefix="/api")
app.include_router(debate.router, prefix="/api")
app.include_router(interview.router, prefix="/api")
app.include_router(coach.router, prefix="/api")
app.include_router(coach.api_router, prefix="/api")
app.include_router(document_analyzer.router, prefix="/api")

@app.get("/")
def read_root():
    return {
        "message": "Welcome to AI Human Communication Twin Platform API!",
        "docs_url": "/docs",
        "status": "active"
    }

@app.get("/health")
def health_check():
    """Standard health probe — returns {status: healthy} when the server is up."""
    return {"status": "healthy"}

@app.get("/debug/system")
def debug_system():
    """
    Diagnostic endpoint that verifies availability of every critical module
    and binary used in the analysis pipeline.  Call this endpoint first
    when the upload/analysis pipeline fails.
    """
    modules = {}

    # Faster-Whisper
    try:
        import faster_whisper  # noqa: F401
        modules["faster_whisper"] = "available"
    except ImportError as e:
        modules["faster_whisper"] = f"MISSING: {e}"

    # OpenCV
    try:
        import cv2  # noqa: F401
        modules["opencv"] = f"available (cv2 {cv2.__version__})"
    except ImportError as e:
        modules["opencv"] = f"MISSING: {e}"

    # MediaPipe
    try:
        import mediapipe  # noqa: F401
        modules["mediapipe"] = f"available ({mediapipe.__version__})"
    except ImportError as e:
        modules["mediapipe"] = f"MISSING: {e}"

    # webrtcvad
    try:
        import webrtcvad  # noqa: F401
        modules["webrtcvad"] = "available"
    except ImportError as e:
        modules["webrtcvad"] = f"MISSING: {e}"

    # numpy
    try:
        import numpy as np  # noqa: F401
        modules["numpy"] = f"available ({np.__version__})"
    except ImportError as e:
        modules["numpy"] = f"MISSING: {e}"

    # FFmpeg binary
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"], capture_output=True, text=True, timeout=5
            )
            version_line = result.stdout.splitlines()[0] if result.stdout else "unknown"
            modules["ffmpeg"] = f"available — {version_line}"
        except Exception as exc:
            modules["ffmpeg"] = f"found at {ffmpeg_path} but version check failed: {exc}"
    else:
        modules["ffmpeg"] = "MISSING — not found in PATH"

    all_ok = all("MISSING" not in v for v in modules.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "modules": modules
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
