"""A complex Python module for testing chunking quality."""

from typing import Optional, List, Dict
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import asyncio
import json

# Constants
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30.0


@dataclass
class Config:
    """Application configuration."""
    host: str = "localhost"
    port: int = 8080
    debug: bool = False
    tags: List[str] = field(default_factory=list)


class BaseService(ABC):
    """Abstract base service with common functionality."""

    def __init__(self, config: Config):
        """Initialize service with config.

        Args:
            config: The service configuration.
        """
        self.config = config
        self._cache: Dict[str, any] = {}

    @abstractmethod
    async def process(self, data: dict) -> dict:
        """Process incoming data."""
        ...

    def _validate(self, data: dict) -> bool:
        """Validate data before processing.

        Checks:
            - Data is not empty
            - Required fields are present
            - Types are correct
        """
        if not data:
            return False
        required = {"id", "type", "payload"}
        return required.issubset(data.keys())


class UserService(BaseService):
    """Service for managing users."""

    async def process(self, data: dict) -> dict:
        if not self._validate(data):
            raise ValueError("Invalid data")

        user_id = data["id"]

        if user_id in self._cache:
            return self._cache[user_id]

        result = await self._fetch_user(user_id)
        self._cache[user_id] = result
        return result

    async def _fetch_user(self, user_id: str) -> dict:
        """Fetch user from database.

        This is a complex operation that:
        1. Connects to the database
        2. Runs the query
        3. Transforms the result
        4. Validates the response
        """
        await asyncio.sleep(0.01)  # Simulated DB call
        return {
            "id": user_id,
            "name": f"User {user_id}",
            "active": True,
        }

    @staticmethod
    def format_user(user: dict) -> str:
        """Format user for display."""
        return f"{user['name']} (ID: {user['id']})"

    class Permissions:
        """Nested class for user permissions."""

        ADMIN = "admin"
        USER = "user"
        GUEST = "guest"

        @classmethod
        def validate(cls, role: str) -> bool:
            return role in (cls.ADMIN, cls.USER, cls.GUEST)


def create_service(config_path: str) -> UserService:
    """Factory function to create a configured UserService."""
    with open(config_path) as f:
        raw = json.load(f)
    config = Config(**raw)
    return UserService(config)


async def main():
    """Entry point."""
    service = create_service("config.json")
    result = await service.process({"id": "123", "type": "user", "payload": {}})
    print(UserService.format_user(result))


if __name__ == "__main__":
    asyncio.run(main())
