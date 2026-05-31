from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.employee import Employee
from app.schemas.employee import EmployeeRead

router = APIRouter()


@router.get("/", response_model=list[EmployeeRead])
async def list_employees(
    department: str | None = Query(None, description="Filter by department name"),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Employee).order_by(Employee.employee_id)
    if department:
        stmt = stmt.where(Employee.department == department)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{employee_id}", response_model=EmployeeRead)
async def get_employee(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Employee).where(Employee.employee_id == employee_id)
    )
    emp = result.scalar_one_or_none()
    if emp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return emp
