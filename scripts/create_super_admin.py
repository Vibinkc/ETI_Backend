"""Script to create the first super admin user."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from app.core.auth import get_password_hash
from app.core.database import DBSessionManager
from app.models.user import User


async def create_super_admin(email: str, password: str, first_name: str, last_name: str) -> None:
    """Create a super admin user."""
    async with DBSessionManager.session() as db:
        # Check if user already exists
        result = await db.execute(select(User).where(User.email == email))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            if existing_user.is_superuser:
                print(f"Super admin with email {email} already exists!")
                return
            # Update existing user to super admin
            existing_user.is_superuser = True
            existing_user.password = get_password_hash(password)
            await db.commit()
            print(f"Updated user {email} to super admin!")
            return

        # Create new super admin
        username = email.split("@")[0]
        slug = username.lower().replace(".", "-").replace("_", "-")
        hashed_password = get_password_hash(password)

        new_admin = User(
            email=email,
            password=hashed_password,
            first_name=first_name,
            last_name=last_name,
            username=username,
            slug=slug,
            is_superuser=True,
        )

        db.add(new_admin)
        await db.commit()
        print("Super admin created successfully!")
        print(f"Email: {email}")
        print(f"Name: {first_name} {last_name}")


async def main() -> None:
    """Read the CLI arguments and create the super admin."""
    if len(sys.argv) < 5:
        print("Usage: python create_super_admin.py <email> <password> <first_name> <last_name>")
        print("Example: python create_super_admin.py admin@example.com password123 John Doe")
        sys.exit(1)

    email = sys.argv[1]
    password = sys.argv[2]
    first_name = sys.argv[3]
    last_name = sys.argv[4]

    await create_super_admin(email, password, first_name, last_name)


if __name__ == "__main__":
    asyncio.run(main())
