from fastapi import APIRouter

from app.api.v1.routes import (
    employees,
    policy,
    receipts,
    reviews,
    submissions,
    verdicts,
)

api_router = APIRouter()

api_router.include_router(employees.router, prefix="/employees", tags=["employees"])
api_router.include_router(policy.router, prefix="/policy", tags=["policy"])
api_router.include_router(submissions.router, prefix="/submissions", tags=["submissions"])
# Receipt upload/list and review live under /submissions/{id}/… so they share the prefix.
api_router.include_router(receipts.router, prefix="/submissions", tags=["receipts"])
api_router.include_router(reviews.router, prefix="/submissions", tags=["reviews"])
# Verdict fetch + override declare their own full paths (/receipts/… and /verdicts/…).
api_router.include_router(verdicts.router, tags=["verdicts"])
