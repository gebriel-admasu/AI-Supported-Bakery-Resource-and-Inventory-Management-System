import enum


class RoleEnum(str, enum.Enum):
    ADMIN = "admin"
    OWNER = "owner"
    PRODUCTION_MANAGER = "production_manager"
    STORE_MANAGER = "store_manager"


class BatchStatus(str, enum.Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DistributionStatus(str, enum.Enum):
    DISPATCHED = "dispatched"
    IN_TRANSIT = "in_transit"
    RECEIVED = "received"
    CONFIRMED = "confirmed"


class WastageReason(str, enum.Enum):
    SPOILAGE = "spoilage"
    DAMAGE = "damage"
    EXPIRY = "expiry"
    PRODUCTION_LOSS = "production_loss"
    OTHER = "other"


class AlertStatus(str, enum.Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class RetrainingTrigger(str, enum.Enum):
    SCHEDULED = "scheduled"
    DATA_THRESHOLD = "data_threshold"
    MANUAL = "manual"


class RetrainingResult(str, enum.Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
