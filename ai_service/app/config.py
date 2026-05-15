from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Bakery AI Forecasting Service"
    DEBUG: bool = True
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/bakery_db"

    MODEL_DIR: str = "trained_models"
    KAGGLE_DATA_PATH: str = "data/store_item_demand"

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


settings = Settings()
