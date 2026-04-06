from fastapi import FastAPI

from app.config import settings
from app.api import predictions, training, models

app = FastAPI(
    title=settings.APP_NAME,
    description="AI demand forecasting microservice for the Bakery Management System",
    version="1.0.0",
)

app.include_router(predictions.router, prefix="/ai", tags=["Predictions"])
app.include_router(training.router, prefix="/ai", tags=["Training"])
app.include_router(models.router, prefix="/ai", tags=["Models"])


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": settings.APP_NAME}
