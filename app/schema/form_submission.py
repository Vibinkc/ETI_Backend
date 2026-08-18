from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class FormSubmissionRequest(BaseModel):
    name: str
    email: EmailStr
    phone: str
    website_url: str | None = None
    user_ip: str | None = None
    user_agent: str | None = None
    session_id: str | None = None


class FormSubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    phone: str
    website_url: str | None
    user_ip: str | None
    user_agent: str | None
    session_id: str | None
    created_at: datetime
