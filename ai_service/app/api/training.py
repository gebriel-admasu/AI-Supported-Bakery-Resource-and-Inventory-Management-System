from fastapi import APIRouter

router = APIRouter()


@router.post("/retrain")
async def trigger_retraining():
    return {"message": "Retraining endpoint - to be implemented in Phase 12"}
