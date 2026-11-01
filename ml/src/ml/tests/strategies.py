"""Generated finite metric scenarios for regression checks."""

from hypothesis import strategies as st
from ml.domain import Metric


def generate_identical_metric_inputs():
    return st.floats(
        min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False
    ).map(build_identical_metric_inputs)


def build_identical_metric_inputs(value: float):
    return (
        dict.fromkeys(Metric, value),
        dict.fromkeys(Metric, value),
        dict.fromkeys(Metric, 0.0),
    )
