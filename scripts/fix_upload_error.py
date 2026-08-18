import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from app.core.auth import get_password_hash
from app.core.database import DBSessionManager
from app.models.user import User


async def fix_superadmin() -> None:
    """Force create the superadmin user to fix upload errors."""

    # Hardcoded credentials from auth.py/admin.py
    email = "superadmin@gmail.com"
    password = "Superadmin@123"

    print(f"Checking for user {email}...")

    async with DBSessionManager.session() as db:
        # Check if user already exists
        result = await db.execute(select(User).where(User.email == email))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            print(f"User {email} already exists with ID: {existing_user.id}")
            if not existing_user.is_superuser:
                print("User exists but is not superuser. Fixing...")
                existing_user.is_superuser = True
                await db.commit()
                print("Fixed: User is now superuser.")
            else:
                print("User is already correctly set up.")
            return

        print("User not found. Creating superadmin user...")

        # Create new super admin
        username = "superadmin"
        slug = "superadmin"
        hashed_password = get_password_hash(password)

        new_admin = User(
            email=email,
            password=hashed_password,
            first_name="Super",
            last_name="Admin",
            username=username,
            slug=slug,
            is_superuser=True,
        )

        db.add(new_admin)
        await db.commit()
        await db.refresh(new_admin)

        print(f"SUCCESS: Super admin created with ID: {new_admin.id}")
        print("Document uploads should now work.")


if __name__ == "__main__":
    try:
        asyncio.run(fix_superadmin())
    except Exception as e:
        print(f"Error running fix script: {e}")
