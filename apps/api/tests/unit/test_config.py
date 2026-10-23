from ragkit_server.core.config import DEV_SECRET, Settings


def test_development_defaults_are_refused_in_production() -> None:
    problems = " ".join(Settings(app_env="production").production_problems())
    for expected in (
        "SESSION_SECRET",
        "API_KEY_PEPPER",
        "COOKIE_SECURE",
        "STORAGE_BACKEND",
        "QUEUE_BACKEND",
    ):
        assert expected in problems


def test_a_real_production_configuration_passes() -> None:
    settings = Settings(
        app_env="production",
        session_secret="s" * 48,
        api_key_pepper="p" * 48,
        cookie_secure=True,
        cors_origins="https://app.ragkit.example.com",
        storage_backend="s3",
        s3_bucket="ragkit-corpus",
        queue_backend="sqs",
        sqs_queue_url="https://sqs.us-east-1.amazonaws.com/000000000000/ragkit-jobs",
    )
    assert settings.production_problems() == []
    assert settings.cors_origins == ["https://app.ragkit.example.com"]


def test_private_url_fetching_and_identical_secrets_are_refused() -> None:
    settings = Settings(
        session_secret="x" * 40, api_key_pepper="x" * 40, url_fetch_allow_private=True
    )
    problems = " ".join(settings.production_problems())
    assert "must differ" in problems
    assert "URL_FETCH_ALLOW_PRIVATE" in problems
    assert Settings().session_secret.get_secret_value() == DEV_SECRET


def test_models_are_optional_and_the_judge_defaults_to_the_answer_model() -> None:
    assert not Settings().models_enabled
    settings = Settings(llm_provider="ollama", llm_model="qwen3:4b")
    assert settings.models_enabled
    assert settings.judge_model_name == "qwen3:4b"
    assert Settings(llm_provider="ollama", llm_model="a", judge_model="b").judge_model_name == "b"
    assert "LLM_MODEL" in " ".join(Settings(llm_provider="openai").production_problems())
