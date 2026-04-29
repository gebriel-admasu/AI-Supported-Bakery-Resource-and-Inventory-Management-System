from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import require_role
from app.core.constants import RoleEnum
from app.models.product import Product
from app.models.recipe import Recipe
from app.models.user import User
from app.schemas.product import ProductCreate, ProductUpdate, ProductResponse

router = APIRouter()


def _product_to_response(db: Session, product: Product) -> dict:
    recipe_name = None
    if product.recipe_id:
        recipe = db.query(Recipe).filter(Recipe.id == product.recipe_id).first()
        if recipe:
            recipe_name = recipe.name
    return {
        "id": product.id,
        "name": product.name,
        "sku": product.sku,
        "sale_price": product.sale_price,
        "unit": product.unit,
        "recipe_id": product.recipe_id,
        "recipe_name": recipe_name,
        "description": product.description,
        "is_active": product.is_active,
        "created_at": product.created_at,
        "updated_at": product.updated_at,
    }


@router.get("/", response_model=List[ProductResponse])
async def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(
            RoleEnum.OWNER,
            RoleEnum.FINANCE_MANAGER,
            RoleEnum.PRODUCTION_MANAGER,
            RoleEnum.STORE_MANAGER,
        )
    ),
):
    query = db.query(Product)
    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))
    if is_active is not None:
        query = query.filter(Product.is_active == is_active)
    products = query.order_by(Product.created_at.desc()).offset(skip).limit(limit).all()
    return [_product_to_response(db, p) for p in products]


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(
            RoleEnum.OWNER,
            RoleEnum.FINANCE_MANAGER,
            RoleEnum.PRODUCTION_MANAGER,
            RoleEnum.STORE_MANAGER,
        )
    ),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return _product_to_response(db, product)


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    body: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    if db.query(Product).filter(Product.sku == body.sku).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A product with this SKU already exists",
        )
    if db.query(Product).filter(Product.name == body.name, Product.is_active == True).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active product with this name already exists",
        )
    if body.recipe_id:
        recipe = db.query(Recipe).filter(Recipe.id == body.recipe_id).first()
        if not recipe:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Recipe not found",
            )

    product = Product(
        name=body.name,
        sku=body.sku,
        sale_price=body.sale_price,
        unit=body.unit,
        recipe_id=body.recipe_id,
        description=body.description,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return _product_to_response(db, product)


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: UUID,
    body: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    update_data = body.model_dump(exclude_unset=True)

    if "sku" in update_data and update_data["sku"] != product.sku:
        if db.query(Product).filter(Product.sku == update_data["sku"], Product.id != product_id).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A product with this SKU already exists",
            )

    if "name" in update_data and update_data["name"] != product.name:
        if db.query(Product).filter(
            Product.name == update_data["name"],
            Product.id != product_id,
            Product.is_active == True,
        ).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An active product with this name already exists",
            )

    if "recipe_id" in update_data and update_data["recipe_id"] is not None:
        if not db.query(Recipe).filter(Recipe.id == update_data["recipe_id"]).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Recipe not found",
            )

    for field, value in update_data.items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return _product_to_response(db, product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_product(
    product_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    product.is_active = False
    db.commit()
    return None
