from fastapi import APIRouter

from app.api.v1 import auth, users, audit, ingredients, stores, inventory, recipes, products, production, wastage, distribution, sales, finance

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(audit.router, prefix="/audit-logs", tags=["Audit Logs"])
api_router.include_router(ingredients.router, prefix="/ingredients", tags=["Ingredients"])
api_router.include_router(stores.router, prefix="/stores", tags=["Stores"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["Inventory"])
api_router.include_router(recipes.router, prefix="/recipes", tags=["Recipes"])
api_router.include_router(products.router, prefix="/products", tags=["Products"])
api_router.include_router(production.router, prefix="/production", tags=["Production"])
api_router.include_router(wastage.router, prefix="/wastage", tags=["Wastage"])
api_router.include_router(distribution.router, prefix="/distributions", tags=["Distributions"])
api_router.include_router(sales.router, prefix="/sales", tags=["Sales"])
api_router.include_router(finance.router, prefix="/finance", tags=["Finance"])
