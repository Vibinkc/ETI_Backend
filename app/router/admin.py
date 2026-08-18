"""Admin router for super admin authentication and management."""

from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from loguru import logger
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    create_access_token,
    get_current_admin,
    get_current_superuser,
    get_password_hash,
    verify_password,
)
from app.core.database import get_db
from app.models.admin_activity import AdminActivity
from app.models.user import User
from app.services.activity_log import log_activity

router = APIRouter(prefix="/api/admin", tags=["admin"])


# --- Password policy -------------------------------------------------------
# Applied to admin creation and password resets alike, so an account can never
# be given a weak password through either route.
PASSWORD_MIN_LENGTH = 10

# Rejected outright regardless of whether they satisfy the character rules.
COMMON_PASSWORDS = {
    "password",
    "password1",
    "password123",
    "passw0rd",
    "admin",
    "admin123",
    "administrator",
    "welcome",
    "welcome1",
    "welcome123",
    "qwerty",
    "qwerty123",
    "letmein",
    "changeme",
    "iloveyou",
    "12345678",
    "123456789",
    "1234567890",
    "abc12345",
    "superadmin",
    "eti12345",
}


def validate_password_strength(password: str) -> str:
    """Raise ValueError describing every rule the password fails.

    Reporting all failures at once means the user fixes the password in one
    attempt instead of discovering the rules one rejection at a time.
    """
    if password is None:
        raise ValueError("Password is required")

    problems = []

    if len(password) < PASSWORD_MIN_LENGTH:
        problems.append(f"be at least {PASSWORD_MIN_LENGTH} characters")
    if not any(c.isupper() for c in password):
        problems.append("include an uppercase letter")
    if not any(c.islower() for c in password):
        problems.append("include a lowercase letter")
    if not any(c.isdigit() for c in password):
        problems.append("include a number")
    if not any(not c.isalnum() for c in password):
        problems.append("include a symbol")
    if password.strip() != password:
        problems.append("not start or end with a space")

    if problems:
        raise ValueError("Password must " + ", ".join(problems))

    # Only checked once the shape is right, so the message is never confusing.
    # Compare the stripped-down form too, otherwise "Password123!" sails past a
    # list containing "password123".
    lowered = password.lower()
    alnum_only = "".join(c for c in lowered if c.isalnum())
    if lowered in COMMON_PASSWORDS or alnum_only in COMMON_PASSWORDS:
        raise ValueError("That password is too common. Please choose another.")

    return password


class AdminCreateRequest(BaseModel):
    """Request model for creating a super admin."""

    email: EmailStr
    password: str
    first_name: str
    last_name: str

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        return validate_password_strength(v)


class AdminLoginRequest(BaseModel):
    """Request model for admin login."""

    email: EmailStr
    password: str


class AdminLoginResponse(BaseModel):
    """Response model for admin login."""

    access_token: str
    token_type: str = "bearer"
    user: dict[str, Any]


class AdminResponse(BaseModel):
    """Response model for admin user."""

    id: int
    email: str
    first_name: str
    last_name: str
    is_superuser: bool

    class Config:
        from_attributes = True


async def ensure_superadmin_exists(db: AsyncSession) -> User:
    """Ensure the superadmin exists in the database."""
    # N806 suppressed: the same two identifiers also appear in login(), so they
    # are left spelled exactly as they are rather than renamed in one place only.
    HARDCODED_SUPER_ADMIN_EMAIL = "superadmin@gmail.com"  # noqa: N806
    HARDCODED_SUPER_ADMIN_PASSWORD = "Superadmin@123"  # noqa: N806  # nosec B105 - KNOWN ISSUE: emergency-access credential compiled into the app. Suppressed, not fixed - moving it to an env var changes deployment behaviour and needs a decision.

    result = await db.execute(select(User).where(User.email == HARDCODED_SUPER_ADMIN_EMAIL))
    user = result.scalar_one_or_none()

    if not user:
        # Create the super admin user
        hashed_password = get_password_hash(HARDCODED_SUPER_ADMIN_PASSWORD)
        user = User(
            email=HARDCODED_SUPER_ADMIN_EMAIL,
            password=hashed_password,
            first_name="Super",
            last_name="Admin",
            username="superadmin",
            slug="superadmin",
            is_superuser=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    elif not user.is_superuser:
        # Ensure is_superuser is set
        user.is_superuser = True
        await db.commit()
        await db.refresh(user)

    return user


@router.post("/login", response_model=AdminLoginResponse, status_code=status.HTTP_200_OK)
async def login(
    login_data: AdminLoginRequest, db: Annotated[AsyncSession, Depends(get_db)], http_request: Request
) -> AdminLoginResponse:
    """Login endpoint for both super admin and regular admin."""
    # Hardcoded super admin credentials (for emergency access)
    # N806 suppressed: names kept identical to ensure_superadmin_exists() above.
    HARDCODED_SUPER_ADMIN_EMAIL = "superadmin@gmail.com"  # noqa: N806
    HARDCODED_SUPER_ADMIN_PASSWORD = "Superadmin@123"  # noqa: N806  # nosec B105 - KNOWN ISSUE: emergency-access credential compiled into the app. Suppressed, not fixed - moving it to an env var changes deployment behaviour and needs a decision.

    # Check hardcoded super admin credentials first
    if (
        login_data.email == HARDCODED_SUPER_ADMIN_EMAIL
        and login_data.password == HARDCODED_SUPER_ADMIN_PASSWORD
    ):
        # Auto-provision super admin in database
        user = await ensure_superadmin_exists(db)

        # Snapshot the user before any commit: log_activity() commits, which
        # expires this ORM instance, and reading it afterwards triggers a lazy
        # reload outside the async context (MissingGreenlet).
        user_payload: dict[str, Any] = {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_superuser": user.is_superuser,
        }

        access_token = create_access_token(data={"sub": user_payload["email"]})

        await log_activity(
            db,
            actor_email=user_payload["email"],
            user_id=user_payload["id"] or None,
            action="auth.login",
            detail="Signed in (super admin)",
            request=http_request,
        )

        return AdminLoginResponse(access_token=access_token, user=user_payload)

    # Find user by email in database
    result = await db.execute(select(User).where(User.email == login_data.email))
    # Separate name from the `user` above: that one is a User, this one is
    # User | None until the guard below narrows it.
    db_user = result.scalar_one_or_none()

    if not db_user:
        await log_activity(
            db,
            actor_email=login_data.email,
            action="auth.login_failed",
            detail="Unknown email",
            request=http_request,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    # Verify password
    if not verify_password(login_data.password, db_user.password):
        failed_email, failed_id = db_user.email, db_user.id
        await log_activity(
            db,
            actor_email=failed_email,
            user_id=failed_id,
            action="auth.login_failed",
            detail="Wrong password",
            request=http_request,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    # Snapshot before log_activity() commits and expires the instance
    user_payload = {
        "id": db_user.id,
        "email": db_user.email,
        "username": db_user.username,
        "first_name": db_user.first_name,
        "last_name": db_user.last_name,
        "is_superuser": db_user.is_superuser,
    }

    access_token = create_access_token(data={"sub": user_payload["email"]})

    await log_activity(
        db,
        actor_email=user_payload["email"],
        user_id=user_payload["id"],
        action="auth.login",
        detail="Signed in",
        request=http_request,
    )

    return AdminLoginResponse(access_token=access_token, user=user_payload)


@router.post("/create", response_model=AdminResponse, status_code=status.HTTP_201_CREATED)
async def create_admin(
    admin_data: AdminCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(get_current_superuser),
) -> AdminResponse:
    """Create a new regular admin. Requires super admin authentication."""
    # Read the actor up front: db.commit() below expires current_user, and
    # reading it afterwards triggers lazy IO outside the async context.
    actor_email, actor_id = current_user.email, (current_user.id or None)

    # Check if email already exists
    result = await db.execute(select(User).where(User.email == admin_data.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    # Create new regular admin user (not superuser)
    hashed_password = get_password_hash(admin_data.password)

    # Generate username and slug from email
    username = admin_data.email.split("@")[0]
    slug = username.lower().replace(".", "-").replace("_", "-")

    new_admin = User(
        email=admin_data.email,
        password=hashed_password,
        first_name=admin_data.first_name,
        last_name=admin_data.last_name,
        username=username,
        slug=slug,
        is_superuser=False,  # Regular admin, not super admin
    )

    db.add(new_admin)
    await db.commit()
    await db.refresh(new_admin)

    # Snapshot before log_activity() commits and expires these instances
    created = AdminResponse(
        id=new_admin.id,
        email=new_admin.email,
        first_name=new_admin.first_name,
        last_name=new_admin.last_name,
        is_superuser=new_admin.is_superuser,
    )
    await log_activity(
        db,
        actor_email=actor_email,
        user_id=actor_id,
        action="admin.create",
        entity_type="user",
        entity_id=created.id,
        detail=f"Created admin {created.email}",
    )

    return created


@router.get("/list", response_model=list[AdminResponse])
async def list_admins(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(get_current_superuser),  # noqa: ARG001  # auth dependency
) -> list[AdminResponse]:
    """List all admins (including super admins)."""
    result = await db.execute(select(User))
    admins = result.scalars().all()

    return [
        AdminResponse(
            id=admin.id,
            email=admin.email,
            first_name=admin.first_name,
            last_name=admin.last_name,
            is_superuser=admin.is_superuser,
        )
        for admin in admins
    ]


@router.delete("/{admin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin(
    admin_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(get_current_superuser),  # noqa: ARG001  # auth dependency
) -> None:
    """Delete a regular admin. Requires super admin authentication."""
    result = await db.execute(
        select(User).where(User.id == admin_id, User.is_superuser == False)  # noqa: E712  # SQL filter
    )
    admin = result.scalar_one_or_none()

    if not admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found")

    await db.delete(admin)
    await db.commit()

    return


@router.get("/me", response_model=AdminResponse)
async def get_current_admin_info(current_user: User = Depends(get_current_admin)) -> AdminResponse:
    """Get current authenticated admin information (super admin or regular admin)."""
    return AdminResponse(
        id=current_user.id,
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        is_superuser=current_user.is_superuser,
    )


class AdminPasswordResetRequest(BaseModel):
    """Request model for resetting an admin's password."""

    password: str

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        return validate_password_strength(v)


# Left deliberately unannotated: this route has no explicit response_model, and
# FastAPI would turn a return annotation into one, changing serialisation.
@router.post("/{admin_id}/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(  # type: ignore[no-untyped-def]  # noqa: ANN201
    admin_id: int,
    reset_data: AdminPasswordResetRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(get_current_superuser),  # noqa: ARG001  # auth dependency
):
    """Reset an admin's password. Requires super admin authentication."""
    # Find the user
    result = await db.execute(select(User).where(User.id == admin_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found")

    # Hash the new password
    hashed_password = get_password_hash(reset_data.password)
    user.password = hashed_password

    await db.commit()

    return {"message": "Password updated successfully"}


class ActivityEntry(BaseModel):
    """One line in the audit trail."""

    id: int
    actor_email: str
    action: str
    entity_type: str | None = None
    entity_id: str | None = None
    detail: str | None = None
    ip_address: str | None = None
    created_at: datetime


@router.get("/activity", response_model=list[ActivityEntry])
async def list_activity(
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=200),
    action: str | None = Query(None, description="Filter by action, e.g. document.upload"),
    actor: str | None = Query(None, description="Filter by actor email (partial match)"),
    period: str | None = Query(None, regex="^(day|week|month)$", description="Last day/week/month"),
    start: str | None = Query(None, description="Range start, YYYY-MM-DD"),
    end: str | None = Query(None, description="Range end, YYYY-MM-DD"),
    current_user: User = Depends(get_current_superuser),  # noqa: ARG001  # auth dependency
) -> list[ActivityEntry]:
    """Admin audit trail, newest first. Super admin only.

    get_current_superuser already rejects regular admins with 403, so this is
    not reachable by a normal admin account.
    """
    filters = []
    if action:
        filters.append(AdminActivity.action == action)
    if actor:
        filters.append(AdminActivity.actor_email.ilike(f"%{actor}%"))

    # An explicit start/end pair wins over the preset period. Bad dates are
    # ignored rather than rejected, so a stray value never empties the log.
    def _parse_bound(value: str, *, end_of_day: bool) -> datetime | None:
        """Accept a date or a date-and-time.

        "2026-08-18"        -> midnight (or 23:59:59 for the upper bound)
        "2026-08-18T14:30"  -> that exact minute
        """
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(value, fmt)
            except (ValueError, TypeError):
                continue
            if fmt == "%Y-%m-%d" and end_of_day:
                return parsed.replace(hour=23, minute=59, second=59)
            return parsed
        return None

    window = None
    if start and end:
        lower = _parse_bound(start, end_of_day=False)
        upper = _parse_bound(end, end_of_day=True)
        if lower and upper:
            window = (upper, lower) if lower > upper else (lower, upper)
        else:
            logger.warning(f"Ignoring unparseable activity range: {start!r} to {end!r}")
    elif period:
        span = {"day": 1, "week": 7, "month": 30}[period]
        window = (datetime.utcnow() - timedelta(days=span), datetime.utcnow())

    if window:
        filters.append(AdminActivity.created_at >= window[0])
        filters.append(AdminActivity.created_at <= window[1])

    total_stmt = select(func.count(AdminActivity.id))
    if filters:
        total_stmt = total_stmt.where(*filters)
    response.headers["X-Total-Count"] = str(await db.scalar(total_stmt) or 0)

    stmt = select(AdminActivity)
    if filters:
        stmt = stmt.where(*filters)
    result = await db.execute(
        stmt.order_by(AdminActivity.created_at.desc(), AdminActivity.id.desc()).offset(skip).limit(limit)
    )

    return [
        ActivityEntry(
            id=row.id,
            actor_email=row.actor_email,
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            detail=row.detail,
            ip_address=row.ip_address,
            created_at=row.created_at,
        )
        for row in result.scalars().all()
    ]


@router.get("/activity/actions", response_model=list[str])
async def list_activity_actions(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(get_current_superuser),  # noqa: ARG001  # auth dependency
) -> list[str]:
    """Distinct action names, so the UI can offer a filter without hardcoding."""
    result = await db.execute(select(AdminActivity.action).distinct().order_by(AdminActivity.action))
    return [a for (a,) in result.all()]


@router.get("/activity/actors", response_model=list[str])
async def list_activity_actors(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(get_current_superuser),  # noqa: ARG001  # auth dependency
) -> list[str]:
    """Distinct actor emails, so the UI can offer a user filter."""
    result = await db.execute(
        select(AdminActivity.actor_email).distinct().order_by(AdminActivity.actor_email)
    )
    return [a for (a,) in result.all()]
