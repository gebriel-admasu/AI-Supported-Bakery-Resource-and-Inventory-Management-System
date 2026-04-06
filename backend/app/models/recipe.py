import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, Numeric, DateTime, ForeignKey, Boolean, Uuid

from app.database import Base


class Recipe(Base):
    __tablename__ = 'recipes'

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    yield_qty = Column(Integer, nullable=False)
    cost_per_unit = Column(Numeric(10, 2), nullable=True)
    instructions = Column(String(2000), nullable=True)
    is_active = Column(Boolean, default=True)
    created_by = Column(Uuid, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class RecipeIngredient(Base):
    __tablename__ = 'recipe_ingredients'

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    recipe_id = Column(Uuid, ForeignKey('recipes.id'), nullable=False)
    ingredient_id = Column(Uuid, ForeignKey('ingredients.id'), nullable=False)
    quantity_required = Column(Numeric(10, 3), nullable=False)
