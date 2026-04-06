from fastapi import APIRouter

router = APIRouter()


@router.post("/predict")
async def predict_demand():
    return {"message": "Demand prediction endpoint - to be implemented in Phase 11"}


@router.get("/forecasts")
async def get_forecasts():
    return {"message": "Forecast listing endpoint - to be implemented in Phase 11"}
