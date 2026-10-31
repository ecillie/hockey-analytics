"""Historical defaults and configurable safety limits retain public behavior."""

from dataclasses import FrozenInstanceError

import pytest

from app.ScriptingFiles.FullDataScript import capspace
from app.ScriptingFiles.FullDataScript.contracts.options import (
    HistoricalContractLimits,
    HistoricalContractOptions,
    ProfileHttpOptions,
    find_option_violation,
)


class TestHistoricalDefaults:
    @pytest.fixture
    def defaults(self):
        return HistoricalContractOptions()

    @pytest.fixture
    def arguments(self):
        return capspace.build_parser().parse_args([])

    def test_command_and_compatibility_exports_share_options_authority(
        self, defaults, arguments
    ):
        assert (
            (
                arguments.first_season,
                arguments.last_season,
                arguments.workers,
                arguments.batch_size,
            )
            == (
                defaults.first_season,
                defaults.last_season,
                defaults.workers,
                defaults.batch_size,
            )
            == (2008, 2025, 4, 100)
        )
        assert (
            capspace.DEFAULT_FIRST_SEASON,
            capspace.DEFAULT_LAST_SEASON,
            capspace.DEFAULT_BATCH_SIZE,
        ) == (defaults.first_season, defaults.last_season, defaults.batch_size)
        assert (
            (capspace.MAX_WORKERS, capspace.MAX_BATCH_SIZE)
            == (defaults.limits.maximum_workers, defaults.limits.maximum_batch_size)
            == (8, 1000)
        )
        with pytest.raises(FrozenInstanceError):
            setattr(defaults.limits, "maximum_workers", 1)

    @pytest.fixture
    def http_options(self):
        return ProfileHttpOptions()

    def test_profile_compatibility_exports_are_derived_from_http_options(
        self, http_options
    ):
        assert capspace.CAPSPACE_BASE_URL == http_options.capspace_base_url
        assert capspace.CAPWAGES_BASE_URL == http_options.capwages_base_url
        assert capspace.RETRYABLE_HTTP_STATUSES == frozenset(
            http_options.retryable_statuses
        )
        assert capspace.CAPWAGES_SLUG_SUFFIXES == http_options.capwages_slug_suffixes

    @pytest.fixture
    def overridden_arguments(self):
        return capspace.build_parser().parse_args(
            [
                "--first-season",
                "2010",
                "--last-season",
                "2012",
                "--workers",
                "2",
                "--batch-size",
                "17",
            ]
        )

    def test_explicit_historical_command_values_remain_historical(
        self, overridden_arguments
    ):
        assert (
            overridden_arguments.first_season,
            overridden_arguments.last_season,
            overridden_arguments.workers,
            overridden_arguments.batch_size,
        ) == (2010, 2012, 2, 17)


class TestHistoricalLimits:
    @pytest.fixture(
        params=[
            pytest.param((1, 1, None), id="lower-boundaries"),
            pytest.param((8, 1000, None), id="upper-boundaries"),
            pytest.param((0, 100, "workers"), id="zero-workers"),
            pytest.param((9, 100, "workers"), id="excess-workers"),
            pytest.param((4, 0, "batch_size"), id="zero-batch"),
            pytest.param((4, 1001, "batch_size"), id="excess-batch"),
        ]
    )
    def scenario(self, request):
        workers, batch, error = request.param
        return HistoricalContractOptions(workers=workers, batch_size=batch), error

    def test_default_limits_preserve_inclusive_boundaries(self, scenario):
        options, error = scenario
        violation = find_option_violation(options)
        if error is None:
            assert violation is None
            return
        assert violation is not None
        assert violation.option == error

    @pytest.fixture
    def overridden_limits(self):
        return HistoricalContractOptions(
            workers=9,
            batch_size=1500,
            limits=HistoricalContractLimits(maximum_workers=9, maximum_batch_size=1500),
        )

    def test_injected_limits_are_the_validation_authority(self, overridden_limits):
        assert find_option_violation(overridden_limits) is None
