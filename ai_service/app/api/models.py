from fastapi import APIRouter

router = APIRouter()


@router.get("/models")
async def list_models():
    return {"message": "Model listing endpoint - to be implemented in Phase 12"}


@router.get("/models/performance")
async def model_performance():
    return {"message": "Model performance endpoint - to be implemented in Phase 12"}
