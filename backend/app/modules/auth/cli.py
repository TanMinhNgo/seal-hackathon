import argparse
import asyncio
from getpass import getpass

from pydantic import ValidationError

from app.core.config import get_settings
from app.core.db import engine, session_factory
from app.core.errors import ApiError
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import RegisterInput
from app.modules.auth.service import AuthService


async def create_admin(data: RegisterInput) -> None:
    try:
        async with session_factory() as session:
            await AuthService(AuthRepository(session), get_settings()).create_first_admin(data)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first SEAL administrator")
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", required=True)
    args = parser.parse_args()
    password = getpass("Password: ")
    if password != getpass("Confirm password: "):
        parser.exit(1, "Passwords do not match\n")
    try:
        data = RegisterInput(email=args.email, full_name=args.full_name, password=password)
        asyncio.run(create_admin(data))
    except ValidationError:
        parser.exit(1, "Invalid email, name or password (8-128 characters)\n")
    except ApiError as exc:
        parser.exit(1, f"{exc.code}: {exc.detail}\n")
    parser.exit(0, "First administrator created\n")


if __name__ == "__main__":
    main()
