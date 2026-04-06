from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import require_role
from app.core.constants import RoleEnum
from app.models.ingredient import Ingredient
from app.models.user import User
from app.schemas.ingredient import IngredientCreate, IngredientResponse, IngredientUpdate

router = APIRouter()


@router.get("/", response_model=List[IngredientResponse])
async def list_ingredients(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    query = db.query(Ingredient)
    if search:
        query = query.filter(Ingredient.name.ilike(f"%{search}%"))
    if is_active is not None:
        query = query.filter(Ingredient.is_active == is_active)
    return query.order_by(Ingredient.created_at.desc()).offset(skip).limit(limit).all()


@router.post("/", response_model=IngredientResponse, status_code=status.HTTP_201_CREATED)
async def create_ingredient(
    body: IngredientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    existing = db.query(Ingredient).filter(Ingredient.name == body.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An ingredient with this name already exists",
        )
    ingredient = Ingredient(
        name=body.name,
        unit=body.unit,
        unit_cost=body.unit_cost,
        expiry_date=body.expiry_date,
        description=body.description,
    )
    db.add(ingredient)
    db.commit()
    db.refresh(ingredient)
    return ingredient


@router.get("/{ingredient_id}", response_model=IngredientResponse)
async def get_ingredient(
    ingredient_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    ingredient = db.query(Ingredient).filter(Ingredient.id == ingredient_id).first()
    if not ingredient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingredient not found")
    return ingredient


@router.put("/{ingredient_id}", response_model=IngredientResponse)
async def update_ingredient(
    ingredient_id: UUID,
    body: IngredientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    ingredient = db.query(Ingredient).filter(Ingredient.id == ingredient_id).first()
    if not ingredient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingredient not found")

    update_data = body.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"] != ingredient.name:
        other = (
            db.query(Ingredient)
            .filter(
                Ingredient.name == update_data["name"],
                Ingredient.id != ingredient_id,
            )
            .first()
        )
        if other:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An ingredient with this name already exists",
            )
    for field, value in update_data.items():
        setattr(ingredient, field, value)
    db.commit()
    db.refresh(ingredient)
    return ingredient


@router.delete("/{ingredient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ingredient(
    ingredient_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    ingredient = db.query(Ingredient).filter(Ingredient.id == ingredient_id).first()
    if not ingredient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingredient not found")
    ingredient.is_active = False
    db.commit()
    return None
