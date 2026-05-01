from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.ingredient import Ingredient
from app.models.recipe import Recipe, RecipeIngredient


def _to_decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def resolve_recipe_unit_cost(db: Session, recipe_id: Optional[UUID]) -> Decimal:
    if not recipe_id:
        return Decimal("0")

    recipe = (
        db.query(Recipe.id, Recipe.yield_qty, Recipe.cost_per_unit)
        .filter(Recipe.id == recipe_id)
        .first()
    )
    if not recipe:
        return Decimal("0")

    total_cost = Decimal("0")
    ingredient_rows = (
        db.query(RecipeIngredient.quantity_required, Ingredient.unit_cost)
        .join(Ingredient, Ingredient.id == RecipeIngredient.ingredient_id)
        .filter(RecipeIngredient.recipe_id == recipe_id)
        .all()
    )
    for quantity_required, ingredient_unit_cost in ingredient_rows:
        total_cost += _to_decimal(quantity_required) * _to_decimal(ingredient_unit_cost)

    yield_qty = int(recipe.yield_qty or 0)
    if yield_qty > 0 and total_cost > 0:
        return (total_cost / Decimal(str(yield_qty))).quantize(Decimal("0.01"))

    return _to_decimal(recipe.cost_per_unit)
