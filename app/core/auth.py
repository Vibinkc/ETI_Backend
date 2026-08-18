"""Authentication utilities for super admin."""

from datetime import timedelta
from typing import Any, cast

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic_settings import BaseSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.timeutils import utcnow
from app.models.user import User


class AuthSettings(BaseSettings):
    """Authentication settings from environment variables."""

    secret_key: str = "your-secret-key-change-in-production-use-env-var"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30 * 24 * 60  # 30 days

    class Config:
        env_file = ".env"
        extra = "ignore"


_auth_settings = AuthSettings()

# JWT settings
SECRET_KEY = _auth_settings.secret_key
ALGORITHM = _auth_settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = _auth_settings.access_token_expire_minutes

# HTTP Bearer token security
security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    try:
        # Decode bytes if needed.
        # The parameters are annotated ``str``, but the isinstance guards below
        # deliberately tolerate callers that already pass ``bytes``. ``cast`` is a
        # runtime no-op that widens the static type so both branches stay
        # reachable for the type checker (``warn_unreachable`` is enabled).
        raw_hashed = cast("str | bytes", hashed_password)
        raw_plain = cast("str | bytes", plain_password)
        if isinstance(raw_hashed, str):
            hashed_bytes = raw_hashed.encode("utf-8")
        else:
            hashed_bytes = raw_hashed
        if isinstance(raw_plain, str):
            plain_bytes = raw_plain.encode("utf-8")
        else:
            plain_bytes = raw_plain
        return bcrypt.checkpw(plain_bytes, hashed_bytes)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Hash a password."""
    # Encode password to bytes. As in verify_password, the isinstance guard
    # tolerates a ``bytes`` argument; the cast only widens the static type.
    raw_password = cast("str | bytes", password)
    if isinstance(raw_password, str):
        password_bytes = raw_password.encode("utf-8")
    else:
        password_bytes = raw_password
    # Generate salt and hash
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    # Return as string
    return hashed.decode("utf-8")


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = utcnow() + expires_delta
    else:
        expire = utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    # python-jose is untyped, so jwt.encode() is inferred as Any. It returns str
    # at runtime; cast rather than str() so a non-str value would surface, not be
    # silently stringified.
    return cast("str", encoded_jwt)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security), db: AsyncSession = Depends(get_db)
) -> User:
    """Get the current authenticated user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # jwt.decode returns Any, and .get() can return None for a token with no
        # "sub" claim. Annotating it str was a lie the guard below immediately
        # contradicts; str | None states what it actually is and narrows to str
        # after the check.
        email: str | None = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    # 1. Try to look up user in database FIRST
    # This ensures we get the real user ID for foreign keys
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user:
        return user

    # 2. Fallback: Check if it's the hardcoded superadmin
    # Only use this if user is NOT in DB
    hardcoded_super_admin_email = "superadmin@gmail.com"

    if email == hardcoded_super_admin_email:
        # Create a mock User object for hardcoded super admin
        hardcoded_admin = User(
            id=0,
            email=hardcoded_super_admin_email,
            username="admin",
            slug="admin",
            first_name="Super",
            last_name="Admin",
            password="",  # nosec B106 - empty by design; this admin never authenticates by hash
            is_superuser=True,
        )
        return hardcoded_admin

    # If neither found
    raise credentials_exception


# NOSONAR - S7503: the `async` is deliberate. FastAPI runs an `async def` dependency
# on the event loop, but dispatches a plain `def` one to the threadpool. Dropping the
# keyword would add a thread hop to every authenticated request to do nothing but
# return a value already resolved by get_current_user.
async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:  # NOSONAR
    """Get the current authenticated admin (super admin or regular admin)."""
    # Both super admin and regular admin can access
    # Regular admin has is_superuser=False, super admin has is_superuser=True
    return current_user


# NOSONAR - S7503: see get_current_admin above. Same FastAPI dispatch reasoning.
async def get_current_superuser(current_user: User = Depends(get_current_user)) -> User:  # NOSONAR
    """Get the current authenticated superuser."""
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return current_user
