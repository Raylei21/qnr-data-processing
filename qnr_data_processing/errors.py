class QnrError(Exception):
    """Base exception for user-facing processing errors."""


class ConfigError(QnrError):
    """The task configuration is invalid or ambiguous."""


class DataValidationError(QnrError):
    """Input files cannot be aligned or validated safely."""


class RuleError(QnrError):
    """A structured rule is invalid or cannot be evaluated."""
