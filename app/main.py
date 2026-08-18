from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from app import logger
from app.core.config import setup_logger
from app.core.manager import lifespan
from app.core.redis import RedisHelper
from app.core.settings import Settings
from app.router.admin import router as admin_router
from app.router.base import router as base_router
from app.router.bot import router as bot_router
from app.router.conversation import router as conversation_router
from app.router.dashboard import router as dashboard_router
from app.router.document import router as document_router
from app.router.form import router as form_router
from app.router.instruction import router as instruction_router
from app.router.widget import router as widget_router

_settings = Settings()

app = FastAPI(lifespan=lifespan, debug=_settings.debug, docs_url="/api/docs")

# Configure CORS to allow frontend requests and external websites
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for embeddable bot (restrict in production)
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, DELETE, etc.)
    allow_headers=["*"],  # Allows all headers
    # Browsers hide non-safelisted response headers unless they are exposed;
    # the documents list returns its unpaginated total in X-Total-Count.
    expose_headers=["X-Total-Count"],
)

setup_logger(_settings.debug)

app.include_router(base_router)
app.include_router(document_router)
app.include_router(bot_router)
app.include_router(widget_router)
app.include_router(conversation_router)
app.include_router(form_router)
app.include_router(dashboard_router)
app.include_router(admin_router)
app.include_router(instruction_router)

# Serve static files (for logo, etc.)
try:
    import os

    static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
except Exception as e:
    logger.warning(f"Could not mount static files: {e}")

client = TestClient(app)


def add_cache_layer(app: FastAPI) -> None:
    try:
        app.state.cache = RedisHelper()
    except Exception as e:
        logger.error(e)
