from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.core.database import get_db, get_db_connect

# For ORM queries
DBSessionDep = Annotated[AsyncSession, Depends(get_db)]

# For Raw SQL queries
DBConnectionDep = Annotated[AsyncConnection, Depends(get_db_connect)]
