import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class EmployeeCreate(BaseModel):
    employee_id: str = Field(..., pattern=r"^NW-\d{5}$")
    name: str
    grade: int = Field(..., ge=1, le=10)
    title: str
    department: str
    manager_id: str | None = Field(None, pattern=r"^NW-\d{5}$")
    home_base: str


class EmployeeRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    employee_id: str
    name: str
    grade: int
    title: str
    department: str
    manager_id: str | None
    home_base: str
    created_at: datetime
