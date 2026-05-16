from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Bakery AI Forecasting Service"
    DEBUG: bool = True

    # The AI service shares the main backend's database so it can read sales_records
    # directly and write its own forecasting tables (model_registry, forecasts,
    # forecast_actuals, mlops_logs) into the same schema. The default path resolves
    # to backend/bakery_dev.db when the service is launched from the ai_service/
    # directory. Override via AI_DATABASE_URL (preferred) or DATABASE_URL in .env.
    AI_DATABASE_URL: str | None = None
    DATABASE_URL: str = "sqlite:///../backend/bakery_dev.db"

    MODEL_DIR: str = "trained_models"
    KAGGLE_DATA_PATH: str = "data/store_item_demand"
    SYNTHETIC_DATA_PATH: str = "data/synthetic/sales.csv"

    # Scheduler cron expressions (5-field cron: m h dom mon dow)
    RETRAIN_SCHEDULE_CRON: str = "0 0 * * 0"   # Sunday 00:00 weekly retrain
    BACKTEST_DAILY_CRON: str = "0 2 * * *"     # Every day at 02:00 — fill actuals for yesterday's forecasts

    # Auto-retraining triggers (FR-54). Threshold = number of NEW SalesRecord rows since last training.
    # We expose a separate DEMO threshold so the project can be defended live without
    # collecting thousands of real sales rows first.
    DEMO_MODE: bool = True
    RETRAIN_VOLUME_THRESHOLD: int = 1000        # production threshold
    RETRAIN_VOLUME_THRESHOLD_DEMO: int = 20     # demo / defense threshold

    # Validation gate (FR-56). Candidate must beat champion by at least this relative MAE drop.
    MAE_IMPROVEMENT_MIN: float = 0.02           # 2% relative improvement
    TTEST_P_VALUE_MAX: float = 0.05             # paired t-test significance level

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def effective_retrain_volume_threshold(self) -> int:
        """Returns the active retraining threshold based on DEMO_MODE.

        In demo mode the threshold is intentionally tiny (~20 rows) so reviewers
        can see the auto-retrain pipeline fire after only a handful of new sales.
        """
        return self.RETRAIN_VOLUME_THRESHOLD_DEMO if self.DEMO_MODE else self.RETRAIN_VOLUME_THRESHOLD

    @property
    def resolved_database_url(self) -> str:
        """Prefer AI_DATABASE_URL (used to point at the backend's SQLite file
        from a different working directory); fall back to DATABASE_URL."""
        return self.AI_DATABASE_URL or self.DATABASE_URL


settings = Settings()
