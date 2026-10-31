"""Structured errors at dataframe boundaries."""


class FrameColumnsError(ValueError):
    def __init__(self, *, missing: tuple[str, ...]) -> None:
        self.missing = missing
        super().__init__(f"Missing frame columns: {missing}")


class FrameGrainError(RuntimeError):
    def __init__(self, *, grain: tuple[str, ...]) -> None:
        self.grain = grain
        super().__init__(f"Frame contains duplicate or missing keys at grain {grain}")


class FrameValuesError(ValueError):
    def __init__(self, *, columns: tuple[str, ...]) -> None:
        self.columns = columns
        super().__init__(f"Non-finite frame values in {columns}")
