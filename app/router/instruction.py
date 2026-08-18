"""Bot instruction router - lets admins edit the chatbot's system prompt."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_admin
from app.core.database import get_db
from app.core.prompts import DEFAULT_SYSTEM_PROMPT
from app.models.bot_instruction import BotInstruction
from app.models.user import User
from app.services.activity_log import log_activity

router = APIRouter(prefix="/api/instructions", tags=["instructions"])


class InstructionResponse(BaseModel):
    """The instruction currently driving the bot."""

    content: str
    is_default: bool
    updated_at: datetime | None = None
    updated_by_email: str | None = None


class InstructionUpdateRequest(BaseModel):
    content: str = Field(min_length=1, description="The system prompt for the chatbot")


async def get_active_instruction(db: AsyncSession) -> BotInstruction | None:
    """Return the stored instruction, or None if an admin has never saved one."""
    result = await db.execute(select(BotInstruction).order_by(BotInstruction.id.desc()).limit(1))
    return result.scalar_one_or_none()


async def get_system_prompt(db: AsyncSession) -> str:
    """Resolve the prompt the bot should use.

    Falls back to DEFAULT_SYSTEM_PROMPT so the bot keeps working even if the
    table is empty or unreachable - the chat must never break over this.
    """
    try:
        instruction = await get_active_instruction(db)
        if instruction and instruction.content.strip():
            return instruction.content
    except Exception as e:
        logger.error(f"Could not load bot instruction, using default: {e}")
    return DEFAULT_SYSTEM_PROMPT


@router.get("", response_model=InstructionResponse)
async def read_instruction(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(get_current_admin),  # noqa: ARG001  # auth guard: FastAPI resolves the admin dependency by parameter name
) -> InstructionResponse:
    """Get the current bot instruction. Falls back to the built-in default."""
    instruction = await get_active_instruction(db)

    if not instruction:
        return InstructionResponse(content=DEFAULT_SYSTEM_PROMPT, is_default=True)

    editor_email = None
    if instruction.updated_by:
        result = await db.execute(select(User).where(User.id == instruction.updated_by))
        editor = result.scalar_one_or_none()
        editor_email = editor.email if editor else None

    return InstructionResponse(
        content=instruction.content,
        is_default=False,
        updated_at=instruction.updated_at,
        updated_by_email=editor_email,
    )


@router.get("/default", response_model=InstructionResponse)
async def read_default_instruction(
    current_user: User = Depends(get_current_admin),  # noqa: ARG001  # auth guard: FastAPI resolves the admin dependency by parameter name
) -> InstructionResponse:
    """Get the built-in default, so the UI can offer a 'reset' action."""
    return InstructionResponse(content=DEFAULT_SYSTEM_PROMPT, is_default=True)


@router.put("", response_model=InstructionResponse)
async def update_instruction(
    payload: InstructionUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(get_current_admin),
) -> InstructionResponse:
    """Create or update the bot instruction. Any admin may edit it."""
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Instructions cannot be empty")

    # Read everything off current_user up front: it is an ORM object attached to
    # this same session, so commit() expires it and any later attribute access
    # would trigger a lazy reload outside the async context (MissingGreenlet).
    #
    # The hardcoded superadmin has id 0 and no matching user row, so storing it
    # would violate the foreign key - record NULL for that case instead.
    editor_id = current_user.id if current_user.id else None
    editor_email = current_user.email

    instruction = await get_active_instruction(db)
    if instruction:
        instruction.content = content
        instruction.updated_by = editor_id
    else:
        instruction = BotInstruction(content=content, updated_by=editor_id)
        db.add(instruction)

    # Flush so server/Python-side defaults are populated, then read the values
    # we need. The session expires attributes on commit, so touching the ORM
    # object afterwards would trigger lazy IO and raise MissingGreenlet.
    await db.flush()
    saved_content = instruction.content
    saved_updated_at = instruction.updated_at
    saved_id = instruction.id

    await db.commit()
    logger.info(f"Bot instruction updated by {editor_email} ({len(content)} chars)")

    await log_activity(
        db,
        actor_email=editor_email,
        user_id=editor_id,
        action="instruction.update",
        entity_type="bot_instruction",
        entity_id=saved_id,
        detail=f"Updated bot instructions ({len(content)} characters)",
    )

    return InstructionResponse(
        content=saved_content, is_default=False, updated_at=saved_updated_at, updated_by_email=editor_email
    )
