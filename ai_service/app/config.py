from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Bakery AI Forecasting Service"
    DEBUG: bool = True
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/bakery_db"
    MODEL_DIR: str = "trained_models"
    RETRAIN_SCHEDULE_CRON: str = "0 0 * * 0"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
