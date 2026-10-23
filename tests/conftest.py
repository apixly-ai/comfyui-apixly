import pytest


@pytest.fixture(autouse=True)
def isolated_account_state(monkeypatch, tmp_path):
    # Unit tests must never read or change an operator's real account binding.
    monkeypatch.setenv("APIXLY_CONNECTION_DIR", str(tmp_path / "private-account"))
