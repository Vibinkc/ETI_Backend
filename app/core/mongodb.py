"""MongoDB connection setup."""

import os
from typing import Any

from dotenv import load_dotenv
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure

load_dotenv()


class MongoDBSettings:
    """MongoDB connection settings."""

    def __init__(self) -> None:
        # Get MongoDB connection details from environment variables
        self.mongo_host = os.getenv("MONGODB_HOST", "localhost")
        self.mongo_port = int(os.getenv("MONGODB_PORT", "27017"))
        # Ensure database name is never empty
        mongo_db_name = os.getenv("MONGODB_DB_NAME", "").strip()
        self.mongo_db_name = mongo_db_name if mongo_db_name else "eti_bot"

        # Construct MongoDB URL
        self.mongo_url = f"mongodb://{self.mongo_host}:{self.mongo_port}"

        self.client: AsyncIOMotorClient[Any] | None = None
        self.db: Any = None

    async def connect(self) -> bool:
        """Connect to MongoDB."""
        try:
            # Validate database name before connecting
            if not self.mongo_db_name or not self.mongo_db_name.strip():
                raise ValueError(
                    "MongoDB database name cannot be empty. Please set MONGODB_DB_NAME environment variable."
                )

            self.client = AsyncIOMotorClient(self.mongo_url)
            # Test connection
            await self.client.admin.command("ping")
            self.db = self.client[self.mongo_db_name]
            logger.info(f"Connected to MongoDB: {self.mongo_host}:{self.mongo_port}/{self.mongo_db_name}")
            return True
        except (ConnectionFailure, ValueError) as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from MongoDB."""
        if self.client:
            self.client.close()
            logger.info("Disconnected from MongoDB")

    def get_database(self) -> Any:
        """Get database instance."""
        if self.db is None:
            raise RuntimeError("MongoDB not connected. Call connect() first.")
        return self.db


# Global MongoDB instance
mongodb_settings = MongoDBSettings()
