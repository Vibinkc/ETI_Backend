"""Form submission API router."""

from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.form_submission import FormSubmission
from app.schema.form_submission import FormSubmissionRequest, FormSubmissionResponse

router = APIRouter(prefix="/api/forms", tags=["forms"])


@router.post("/submit", response_model=FormSubmissionResponse, status_code=status.HTTP_201_CREATED)
async def submit_form(
    form_data: FormSubmissionRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> FormSubmission:
    """Submit a form from the bot widget."""
    try:
        # Get IP address if not provided
        user_ip = form_data.user_ip
        if not user_ip:
            user_ip = request.client.host if request.client else None

        # Get user agent if not provided
        user_agent = form_data.user_agent
        if not user_agent:
            user_agent = request.headers.get("user-agent")

        # Create form submission
        form_submission = FormSubmission(
            name=form_data.name,
            email=form_data.email,
            phone=form_data.phone,
            website_url=form_data.website_url,
            user_ip=user_ip,
            user_agent=user_agent,
            session_id=form_data.session_id,
        )

        db.add(form_submission)
        await db.commit()
        await db.refresh(form_submission)

        logger.info(f"Form submission created: {form_submission.id} - {form_submission.email}")

        return form_submission

    except Exception as e:
        logger.error(f"Error submitting form: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error submitting form: {e!s}"
        ) from e


@router.get("/", response_model=list[FormSubmissionResponse])
async def get_form_submissions(
    skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
) -> Sequence[FormSubmission]:
    """Get all form submissions."""
    try:
        result = await db.execute(
            select(FormSubmission).order_by(FormSubmission.created_at.desc()).offset(skip).limit(limit)
        )
        submissions = result.scalars().all()
        return submissions
    except Exception as e:
        logger.error(f"Error fetching form submissions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching form submissions: {e!s}",
        ) from e


@router.delete("/{submission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_form_submission(submission_id: int, db: AsyncSession = Depends(get_db)) -> None:
    """Delete a form submission."""
    try:
        result = await db.execute(select(FormSubmission).where(FormSubmission.id == submission_id))
        submission = result.scalar_one_or_none()

        if not submission:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Form submission not found")

        await db.delete(submission)
        await db.commit()

        logger.info(f"Form submission deleted: {submission_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting form submission: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error deleting form submission: {e!s}"
        ) from e
