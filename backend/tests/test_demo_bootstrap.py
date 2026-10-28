import pytest

from scripts import create_demo_user


@pytest.mark.asyncio
async def test_demo_bootstrap_is_development_only_and_rejects_short_passwords(monkeypatch):
    monkeypatch.setattr(create_demo_user.settings, "APP_ENV", "production")
    with pytest.raises(RuntimeError, match="only when APP_ENV=development"):
        await create_demo_user.setup_demo_account("admin@example.com", "long-enough-password")

    monkeypatch.setattr(create_demo_user.settings, "APP_ENV", "development")
    with pytest.raises(ValueError, match="at least 15 characters"):
        await create_demo_user.setup_demo_account("admin@example.com", "too-short")


def test_demo_bootstrap_prompts_for_login_and_never_prints_password(monkeypatch, capsys):
    password = "private-local-password-123"
    captured = {}

    async def capture_setup(*, email, password):
        captured.update(email=email, password=password)

    monkeypatch.setattr(create_demo_user.settings, "APP_ENV", "development")
    monkeypatch.setattr(create_demo_user, "setup_demo_account", capture_setup)
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    prompted_passwords = iter([password, password])
    monkeypatch.setattr(create_demo_user.getpass, "getpass", lambda _prompt: next(prompted_passwords))
    create_demo_user.main()

    assert captured == {"email": "admin@example.com", "password": password}
    assert password not in capsys.readouterr().out
