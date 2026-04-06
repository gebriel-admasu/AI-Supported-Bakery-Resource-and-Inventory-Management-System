from typing import List, Optional
from uuid import UUID
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import require_role
from app.core.constants import RoleEnum
from app.models.recipe import Recipe, RecipeIngredient
from app.models.ingredient import Ingredient
from app.models.user import User
from app.schemas.recipe import (
    RecipeCreate,
    RecipeUpdate,
    RecipeResponse,
    RecipeIngredientResponse,
)

router = APIRouter()


def _build_recipe_response(db: Session, recipe: Recipe) -> dict:
    ri_rows = (
        db.query(RecipeIngredient, Ingredient)
        .outerjoin(Ingredient, RecipeIngredient.ingredient_id == Ingredient.id)
        .filter(RecipeIngredient.recipe_id == recipe.id)
        .all()
    )

    ingredients: list[RecipeIngredientResponse] = []
    total_cost = Decimal("0")

    for ri, ing in ri_rows:
        unit_cost = ing.unit_cost if ing else Decimal("0")
        line_cost = Decimal(str(ri.quantity_required)) * Decimal(str(unit_cost))
        total_cost += line_cost
        ingredients.append(
            RecipeIngredientResponse(
                id=ri.id,
                ingredient_id=ri.ingredient_id,
                ingredient_name=ing.name if ing else None,
                ingredient_unit=ing.unit if ing else None,
                ingredient_unit_cost=unit_cost if ing else None,
                quantity_required=ri.quantity_required,
            )
        )

    cost_per_unit = (
        (total_cost / recipe.yield_qty).quantize(Decimal("0.01"))
        if recipe.yield_qty and recipe.yield_qty > 0
        else None
    )

    return {
        "id": recipe.id,
        "name": recipe.name,
        "version": recipe.version,
        "yield_qty": recipe.yield_qty,
        "cost_per_unit": cost_per_unit,
        "instructions": recipe.instructions,
        "is_active": recipe.is_active,
        "created_by": recipe.created_by,
        "ingredients": ingredients,
        "created_at": recipe.created_at,
        "updated_at": recipe.updated_at,
    }


@router.get("/", response_model=List[RecipeResponse])
async def list_recipes(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    query = db.query(Recipe)
    if search:
        query = query.filter(Recipe.name.ilike(f"%{search}%"))
    if is_active is not None:
        query = query.filter(Recipe.is_active == is_active)
    recipes = query.order_by(Recipe.updated_at.desc()).offset(skip).limit(limit).all()
    return [_build_recipe_response(db, r) for r in recipes]


@router.get("/{recipe_id}", response_model=RecipeResponse)
async def get_recipe(
    recipe_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")
    return _build_recipe_response(db, recipe)


@router.post("/", response_model=RecipeResponse, status_code=status.HTTP_201_CREATED)
async def create_recipe(
    body: RecipeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    existing = db.query(Recipe).filter(Recipe.name == body.name, Recipe.is_active == True).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active recipe with this name already exists",
        )

    for item in body.ingredients:
        ing = db.query(Ingredient).filter(Ingredient.id == item.ingredient_id).first()
        if not ing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ingredient {item.ingredient_id} not found",
            )

    recipe = Recipe(
        name=body.name,
        yield_qty=body.yield_qty,
        instructions=body.instructions,
        created_by=current_user.id,
    )
    db.add(recipe)
    db.flush()

    for item in body.ingredients:
        ri = RecipeIngredient(
            recipe_id=recipe.id,
            ingredient_id=item.ingredient_id,
            quantity_required=item.quantity_required,
        )
        db.add(ri)

    db.commit()
    db.refresh(recipe)
    return _build_recipe_response(db, recipe)


@router.put("/{recipe_id}", response_model=RecipeResponse)
async def update_recipe(
    recipe_id: UUID,
    body: RecipeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")

    update_data = body.model_dump(exclude_unset=True)

    if "name" in update_data and update_data["name"] != recipe.name:
        other = (
            db.query(Recipe)
            .filter(Recipe.name == update_data["name"], Recipe.id != recipe_id, Recipe.is_active == True)
            .first()
        )
        if other:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An active recipe with this name already exists",
            )

    ingredients_payload = update_data.pop("ingredients", None)

    for field, value in update_data.items():
        setattr(recipe, field, value)

    if ingredients_payload is not None:
        for item in ingredients_payload:
            ing = db.query(Ingredient).filter(Ingredient.id == item.ingredient_id).first()
            if not ing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Ingredient {item.ingredient_id} not found",
                )

        db.query(RecipeIngredient).filter(RecipeIngredient.recipe_id == recipe.id).delete()
        for item in ingredients_payload:
            ri = RecipeIngredient(
                recipe_id=recipe.id,
                ingredient_id=item.ingredient_id,
                quantity_required=item.quantity_required,
            )
            db.add(ri)
        recipe.version = (recipe.version or 1) + 1

    db.commit()
    db.refresh(recipe)
    return _build_recipe_response(db, recipe)


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_recipe(
    recipe_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")
    recipe.is_active = False
    db.commit()
    return None
