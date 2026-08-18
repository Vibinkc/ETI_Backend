from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    debug: bool = False
    app_env: str = "development"

    class config:  # noqa: N801
        env_file = ".env"
        extra = "ignore"


settings = Settings()
