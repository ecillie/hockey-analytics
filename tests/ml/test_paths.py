"""External artifact path behavior across working directories."""

from pathlib import Path
import pytest
from ml.paths import resolve_artifact_directory


class TestArtifactDirectories:
    default_directory = Path("models")
    source_directory = Path(__file__).parents[2].joinpath("ml", "models")

    @pytest.fixture
    def outside_checkout(self, monkeypatch, tmp_path):
        monkeypatch.delenv("TRADEVALUE_MODEL_DIR", raising=False)
        monkeypatch.chdir(tmp_path)

    @pytest.mark.usefixtures("outside_checkout")
    def test_source_destination_is_independent_of_working_directory(self):
        destination = resolve_artifact_directory(
            "TRADEVALUE_MODEL_DIR", self.default_directory
        )
        assert destination == self.source_directory

    @pytest.fixture
    def configured_directory(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRADEVALUE_MODEL_DIR", str(tmp_path))
        return tmp_path

    def test_explicit_external_destination(self, configured_directory):
        assert (
            resolve_artifact_directory("TRADEVALUE_MODEL_DIR", self.default_directory)
            == configured_directory
        )
