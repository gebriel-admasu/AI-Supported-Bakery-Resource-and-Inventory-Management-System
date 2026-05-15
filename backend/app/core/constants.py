import enum


class RoleEnum(str, enum.Enum):
    ADMIN = "admin"
    OWNER = "owner"
    FINANCE_MANAGER = "finance_manager"
    PRODUCTION_MANAGER = "production_manager"
    STORE_MANAGER = "store_manager"
    DELIVERY_STAFF = "delivery_staff"


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


class DiscrepancyStatus(str, enum.Enum):
    NONE = "none"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


class PurchaseOrderStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    SENT = "sent"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class WastageReason(str, enum.Enum):
    SPOILAGE = "spoilage"
    DAMAGE = "damage"
    EXPIRY = "expiry"
    PRODUCTION_LOSS = "production_loss"
    OTHER = "other"


class WastageSourceType(str, enum.Enum):
    STORE = "store"
    PRODUCTION = "production"


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
