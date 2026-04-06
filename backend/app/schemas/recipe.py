from typing import Optional, List
from uuid import UUID
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class RecipeIngredientPayload(BaseModel):
    ingredient_id: UUID
    quantity_required: Decimal


class RecipeCreate(BaseModel):
    name: str
    yield_qty: int
    instructions: Optional[str] = None
    ingredients: List[RecipeIngredientPayload] = []


class RecipeUpdate(BaseModel):
    name: Optional[str] = None
    yield_qty: Optional[int] = None
    instructions: Optional[str] = None
    is_active: Optional[bool] = None
    ingredients: Optional[List[RecipeIngredientPayload]] = None


class RecipeIngredientResponse(BaseModel):
    id: UUID
    ingredient_id: UUID
    ingredient_name: Optional[str] = None
    ingredient_unit: Optional[str] = None
    ingredient_unit_cost: Optional[Decimal] = None
    quantity_required: Decimal

    model_config = {"from_attributes": True}


class RecipeResponse(BaseModel):
    id: UUID
    name: str
    version: int
    yield_qty: int
    cost_per_unit: Optional[Decimal] = None
    instructions: Optional[str] = None
    is_active: bool
    created_by: Optional[UUID] = None
    ingredients: List[RecipeIngredientResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
