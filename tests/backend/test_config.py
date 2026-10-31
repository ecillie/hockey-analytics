"""Configuration precedence, escaping, and validation at explicit boundaries."""

import pytest

from app.config import (
    AppEnvironment,
    ConfigurationError,
    get_api_settings,
    get_database_settings,
)


class TestDatabaseSettings:
    @pytest.fixture
    def url_settings(self):
        return get_database_settings(
            {
                "DATABASE_URL": "postgresql://example.test/tradevalue",
                "ENV": "nonprod",
                "DB_USER": "ignored",
                "DB_NAME": "ignored",
                "DB_CONNECT_TIMEOUT": "7",
            }
        )

    def test_database_url_takes_precedence(self, url_settings):
        assert url_settings.database_url == "postgresql://example.test/tradevalue"
        assert url_settings.environment == AppEnvironment.NONPROD
        assert url_settings.connect_timeout_seconds == 7
        assert url_settings.pool_size == 2
        assert url_settings.max_overflow == 3
        assert url_settings.pool_recycle_seconds == 300

    @pytest.fixture
    def component_settings(self):
        return get_database_settings(
            {
                "ENV": "dev",
                "DB_USER": "trade value",
                "DB_PASSWORD": "secret/@word",
                "DB_HOST": "localhost",
                "DB_PORT": "5433",
                "DB_NAME": "hockey data",
            }
        )

    def test_component_settings_are_url_encoded(self, component_settings):
        assert component_settings.database_url == (
            "postgresql://trade%20value:secret%2F%40word@localhost:5433/hockey%20data"
        )

    @pytest.fixture
    def scoped_settings(self):
        return get_database_settings(
            {
                "ENV": "prod",
                "PROD_DATABASE_URL": "postgresql://prod.test/tradevalue",
                "NONPROD_DATABASE_URL": "postgresql://nonprod.test/tradevalue",
                "DATABASE_URL": "postgresql://fallback.test/tradevalue",
            }
        )

    def test_scoped_url_matches_selected_environment(self, scoped_settings):
        assert scoped_settings.database_url == "postgresql://prod.test/tradevalue"

    @pytest.fixture(
        params=[
            pytest.param(({"ENV": "prod"}, "DATABASE_URL"), id="missing-database-url"),
            pytest.param(
                (
                    {"DATABASE_URL": "postgresql://example.test/db"},
                    "ENV must be one of",
                ),
                id="missing-environment",
            ),
            pytest.param(
                (
                    {
                        "ENV": "prod",
                        "DATABASE_URL": "postgresql://example.test/db",
                        "DB_POOL_SIZE": "0",
                    },
                    "DB_POOL_SIZE",
                ),
                id="empty-pool",
            ),
        ]
    )
    def invalid_settings(self, request):
        return request.param

    def test_invalid_database_settings_are_rejected(self, invalid_settings):
        environment, message = invalid_settings
        with pytest.raises(ConfigurationError, match=message):
            get_database_settings(environment)


class TestApiSettings:
    pattern = r"^https://trade-[a-z0-9-]+\.vercel\.app$"

    @pytest.fixture
    def cors_settings(self):
        return get_api_settings(
            {"CORS_ORIGINS": "https://trade.example, https://preview.example"}
        )

    def test_api_cors_origins_are_trimmed(self, cors_settings):
        assert cors_settings.cors_origins == (
            "https://trade.example",
            "https://preview.example",
        )
        assert cors_settings.cors_origin_regex is None

    @pytest.fixture
    def preview_settings(self):
        return get_api_settings(
            {"CORS_ORIGINS": "https://trade.example", "CORS_ORIGIN_REGEX": self.pattern}
        )

    def test_api_cors_preview_regex_is_optional(self, preview_settings):
        assert preview_settings.cors_origin_regex == self.pattern
