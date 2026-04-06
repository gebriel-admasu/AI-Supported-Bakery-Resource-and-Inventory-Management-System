from typing import List

from fastapi import Depends, HTTPException, status

from app.core.constants import RoleEnum


ROLE_PERMISSIONS = {
    RoleEnum.ADMIN: [
        "manage_users", "view_audit_logs", "system_config",
    ],
    RoleEnum.OWNER: [
        "manage_ingredients", "edit_ingredients", "delete_ingredients",
        "manage_recipes", "manage_products",
        "view_inventory", "adjust_inventory", "set_thresholds",
        "view_production", "manage_production",
        "view_all_sales", "view_all_stores",
        "manage_distribution",
        "view_financials", "manage_pricing",
        "manage_suppliers",
        "view_forecasts", "view_reports", "export_reports",
        "view_dashboard", "view_mlops",
    ],
    RoleEnum.PRODUCTION_MANAGER: [
        "manage_ingredients", "view_inventory",
        "manage_recipes", "manage_products",
        "view_production", "manage_production",
        "manage_distribution",
        "view_forecasts",
        "view_dashboard",
    ],
    RoleEnum.STORE_MANAGER: [
        "view_own_store",
        "record_sales", "record_opening_stock", "record_closing_stock",
        "record_wastage",
        "confirm_receipt",
        "view_own_reports",
        "view_dashboard",
    ],
}


def has_permission(role: RoleEnum, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, [])


def check_permissions(required_permissions: List[str]):
    """Dependency generator that checks if the current user has required permissions."""
    from app.api.deps import get_current_user

    async def permission_checker(current_user=Depends(get_current_user)):
        user_role = RoleEnum(current_user.role)
        for perm in required_permissions:
            if not has_permission(user_role, perm):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {perm} required",
                )
        return current_user

    return permission_checker
