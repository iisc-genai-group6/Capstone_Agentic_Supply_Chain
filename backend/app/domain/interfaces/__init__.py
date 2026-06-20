"""Domain interfaces (ports)."""

from app.domain.interfaces.repositories import IRepository
from app.domain.interfaces.services import IService

__all__ = ["IRepository", "IService"]
