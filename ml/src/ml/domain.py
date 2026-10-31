"""Published model split and metric identifiers."""

from enum import StrEnum, auto


class Split(StrEnum):
    TRAIN = auto()
    VALIDATION = auto()
    TEST = auto()


class Metric(StrEnum):
    MAE = auto()
    RMSE = auto()
    R2 = auto()
