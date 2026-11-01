"""Typed failures for diagnostic settings and process handler ownership."""


class LoggingSettingsError(ValueError):
    def __init__(self, *, field: str, choices: str) -> None:
        super().__init__(f"{field} must be one of: {choices}")
        self.field = field
        self.choices = choices


class LoggingOwnershipError(RuntimeError):
    def __init__(self, *, name: str) -> None:
        super().__init__(
            f"Diagnostic handler name {name} is already owned by another configuration"
        )
        self.name = name


class LoggingConfigurationConflictError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "Logging settings changed within one process; restart to apply new settings"
        )


class RecordLimitsError(ValueError):
    def __init__(self, *, field: str, minimum: int, maximum: int) -> None:
        super().__init__(f"{field} must be between {minimum} and {maximum}")
        self.field = field
        self.minimum = minimum
        self.maximum = maximum
