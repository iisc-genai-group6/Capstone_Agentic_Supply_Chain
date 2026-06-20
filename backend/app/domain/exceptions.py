"""Domain exceptions."""


class DomainError(Exception):
    """Base domain exception."""


class EntityNotFoundError(DomainError):
    """Raised when a requested entity does not exist."""

    def __init__(self, entity_name: str, entity_id: str | None = None) -> None:
        message = f"{entity_name} not found"
        if entity_id:
            message = f"{entity_name} with id '{entity_id}' not found"
        super().__init__(message)
        self.entity_name = entity_name
        self.entity_id = entity_id


class ValidationError(DomainError):
    """Raised when domain validation fails."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field
