from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{report_id}")
async def get_report(report_id: str):
    """Get a report by ID."""
    raise HTTPException(status_code=501, detail="Not implemented yet")
