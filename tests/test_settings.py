from webapp.settings import load_settings


def test_load_settings_uses_standard_dotenv_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("ENV=local\nKITE_API_KEY=test-key\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ENV", raising=False)

    settings = load_settings()

    assert settings.environment == "local"


def test_load_settings_accepts_container_environment_without_env_file(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ENV", "docker")

    settings = load_settings()

    assert settings.environment == "docker"
