import pytest

from main import production_oauth_provider


def test_no_provider_keeps_reboots_own_safeguard(monkeypatch: pytest.MonkeyPatch) -> None:
    # `prod=None` is what makes `rbt serve` refuse to start rather than
    # quietly shipping the development account picker.
    monkeypatch.delenv("OAUTH_PROVIDER", raising=False)
    assert production_oauth_provider() is None


def test_credentials_are_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OAUTH_PROVIDER", "google")
    monkeypatch.setenv("OAUTH_CLIENT_ID", "")
    monkeypatch.setenv("OAUTH_CLIENT_SECRET", "")
    with pytest.raises(ValueError, match="OAUTH_CLIENT_ID"):
        production_oauth_provider()


def test_tenant_hosted_providers_need_a_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OAUTH_PROVIDER", "auth0")
    monkeypatch.setenv("OAUTH_CLIENT_ID", "id")
    monkeypatch.setenv("OAUTH_CLIENT_SECRET", "secret")
    monkeypatch.delenv("OAUTH_DOMAIN", raising=False)
    with pytest.raises(ValueError, match="OAUTH_DOMAIN"):
        production_oauth_provider()


def test_a_typo_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OAUTH_PROVIDER", "googel")
    monkeypatch.setenv("OAUTH_CLIENT_ID", "id")
    monkeypatch.setenv("OAUTH_CLIENT_SECRET", "secret")
    with pytest.raises(ValueError, match="Unknown OAUTH_PROVIDER"):
        production_oauth_provider()


@pytest.mark.parametrize("name", ["google", "github"])
def test_hosted_providers_build(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setenv("OAUTH_PROVIDER", name)
    monkeypatch.setenv("OAUTH_CLIENT_ID", "id")
    monkeypatch.setenv("OAUTH_CLIENT_SECRET", "secret")
    assert production_oauth_provider() is not None


def test_auth0_builds_with_a_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OAUTH_PROVIDER", "auth0")
    monkeypatch.setenv("OAUTH_CLIENT_ID", "id")
    monkeypatch.setenv("OAUTH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("OAUTH_DOMAIN", "tenant.eu.auth0.com")
    assert production_oauth_provider() is not None
