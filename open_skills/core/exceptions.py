"""
Custom exceptions for open-skills.
"""


class OpenSkillsError(Exception):
    """Base exception for all open-skills errors."""

    pass


class ConfigurationError(OpenSkillsError):
    """Raised when configuration is invalid or missing."""

    pass


class SkillNotFoundError(OpenSkillsError):
    """Raised when a skill is not found."""

    pass


class SkillVersionNotFoundError(OpenSkillsError):
    """Raised when a skill version is not found."""

    pass


class SkillValidationError(OpenSkillsError):
    """Raised when skill bundle validation fails."""

    pass


class SkillExecutionError(OpenSkillsError):
    """Raised when skill execution fails."""

    pass


class SkillTimeoutError(SkillExecutionError):
    """Raised when skill execution exceeds timeout."""

    pass


class ArtifactError(OpenSkillsError):
    """Raised when artifact handling fails."""

    pass


class ArtifactSizeExceededError(ArtifactError):
    """Raised when artifact size exceeds limit."""

    pass


class PermissionDeniedError(OpenSkillsError):
    """Raised when user lacks required permissions."""

    pass


class AuthenticationError(OpenSkillsError):
    """Raised when authentication fails."""

    pass


class RateLimitError(OpenSkillsError):
    """Raised when rate limit is exceeded."""

    pass


class StorageError(OpenSkillsError):
    """Raised when storage operations fail."""

    pass


class EmbeddingError(OpenSkillsError):
    """Raised when embedding generation fails."""

    pass


class InvalidInputError(OpenSkillsError):
    """Raised when input validation fails."""

    pass


class RunNotFoundError(OpenSkillsError):
    """Raised when a run is not found."""

    pass
