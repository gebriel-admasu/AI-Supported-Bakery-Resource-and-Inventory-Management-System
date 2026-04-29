"""
Seed script to create initial admin user and sample data.

Usage:
    cd backend
    python -m app.seed
"""

from app.database import SessionLocal, engine, Base
from app.models import User, Store
from app.core.security import hash_password
from app.core.constants import RoleEnum


def seed_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        existing_admin = db.query(User).filter(User.role == RoleEnum.ADMIN).first()
        if existing_admin:
            print("Admin user already exists. Skipping seed.")
            return

        admin = User(
            username="admin",
            email="admin@bakery.com",
            password_hash=hash_password("admin123"),
            full_name="System Administrator",
            role=RoleEnum.ADMIN,
            is_active=True,
        )
        db.add(admin)

        owner = User(
            username="owner",
            email="owner@bakery.com",
            password_hash=hash_password("owner123"),
            full_name="Bakery Owner",
            role=RoleEnum.OWNER,
            is_active=True,
        )
        db.add(owner)

        main_store = Store(name="Main Store", location="Addis Ababa - Bole")
        branch_store = Store(name="Branch Store", location="Addis Ababa - Piazza")
        db.add(main_store)
        db.add(branch_store)
        db.flush()

        prod_manager = User(
            username="production",
            email="production@bakery.com",
            password_hash=hash_password("prod123"),
            full_name="Production Manager",
            role=RoleEnum.PRODUCTION_MANAGER,
            is_active=True,
        )
        db.add(prod_manager)

        store_manager = User(
            username="storemanager",
            email="store@bakery.com",
            password_hash=hash_password("store123"),
            full_name="Store Manager",
            role=RoleEnum.STORE_MANAGER,
            is_active=True,
            store_id=main_store.id,
        )
        db.add(store_manager)

        delivery_staff = User(
            username="delivery1",
            email="delivery@bakery.com",
            password_hash=hash_password("delivery123"),
            full_name="Delivery Staff",
            role=RoleEnum.DELIVERY_STAFF,
            is_active=True,
        )
        db.add(delivery_staff)

        finance_manager = User(
            username="finance1",
            email="finance@bakery.com",
            password_hash=hash_password("finance123"),
            full_name="Finance Manager",
            role=RoleEnum.FINANCE_MANAGER,
            is_active=True,
        )
        db.add(finance_manager)

        db.commit()
        print("Database seeded successfully!")
        print("  Admin:    admin / admin123")
        print("  Owner:    owner / owner123")
        print("  ProdMgr:  production / prod123")
        print("  StoreMgr: storemanager / store123")
        print("  Delivery: delivery1 / delivery123")
        print("  Finance:  finance1 / finance123")
        print(f"  Stores:   {main_store.name}, {branch_store.name}")

    except Exception as e:
        db.rollback()
        print(f"Seed failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_db()
