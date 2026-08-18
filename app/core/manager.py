import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from app.core.database import DBSessionManager
from app.core.mongodb import mongodb_settings
from app.router.admin import ensure_superadmin_exists

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[Any]:  # noqa: ARG001
    """
    To handles startup and shutdown events.
    """
    # Connect to MongoDB on startup
    await mongodb_settings.connect()

    # Ensure superadmin exists (startup migration)
    try:
        async with DBSessionManager.session() as db:
            logger.info("Checking superadmin status...")
            await ensure_superadmin_exists(db)
            logger.info("Superadmin check completed.")
    except Exception as e:
        logger.error(f"Error checking superadmin on startup: {e}")

    yield

    # Cleanup on shutdown
    if DBSessionManager.engine is not None:
        # Close the DB connection
        await DBSessionManager.close()

    # Disconnect from MongoDB
    await mongodb_settings.disconnect()
