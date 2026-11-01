"""Generated finite metric scenarios for regression checks."""

from hypothesis import strategies as st
from ml.domain import Metric
from ml.tests.fakes import MetricScenario


def generate_identical_metric_inputs():
    return st.floats(
        min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False
    ).map(build_identical_metric_inputs)


def build_identical_metric_inputs(value: float):
    return MetricScenario(
        current=dict.fromkeys(Metric, value),
        baseline=dict.fromkeys(Metric, value),
        tolerances=dict.fromkeys(Metric, 0.0),
    )
