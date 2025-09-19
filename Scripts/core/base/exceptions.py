"""Custom exceptions for the API processing system."""

class ProcessingError(Exception):
    """Base exception for processing errors."""
    pass

class ValidationError(ProcessingError):
    """Raised when file validation fails."""
    pass

class APIError(ProcessingError):
    """Raised when API calls fail."""
    pass

class ConfigurationError(ProcessingError):
    """Raised when configuration is invalid."""
    pass
