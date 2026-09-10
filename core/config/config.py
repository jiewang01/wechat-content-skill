from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class AccountEnv(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_id: str = Field(description="Environment variable name holding the WeChat app id.")
    app_secret: str = Field(description="Environment variable name holding the WeChat app secret.")


class AccountConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    env: AccountEnv


class RunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme: str = "default"
    account: str = "default"
    outputs_dir: Path = Path("outputs")
    accounts_dir: Path = Path("accounts")


def load_account(accounts_dir: Path | str, account: str = "default") -> AccountConfig:
    path = Path(accounts_dir) / f"{account}.yaml"
    if not path.exists():
        path = Path(accounts_dir) / f"{account}.yml"
    if not path.exists():
        raise FileNotFoundError(
            f"account config not found: {Path(accounts_dir) / account}.yaml "
            f"(see accounts/accounts.example.yaml; secrets live in env vars only)"
        )
    return AccountConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def resolve_credentials(account_config: AccountConfig) -> tuple[str, str]:
    app_id = os.environ.get(account_config.env.app_id, "")
    app_secret = os.environ.get(account_config.env.app_secret, "")
    if not app_id or not app_secret:
        raise RuntimeError(
            f"missing credentials for account '{account_config.name}': "
            f"set {account_config.env.app_id} and {account_config.env.app_secret}"
        )
    return app_id, app_secret


__all__ = ["AccountConfig", "AccountEnv", "RunConfig", "load_account", "resolve_credentials"]
