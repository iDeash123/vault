import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from scripts.verify_no_comments import check_frontend_file, check_python_file

from core.clock import FrozenClock, SystemClock
from core.config import Settings
from core.exceptions import DomainError, NotFoundError


def test_settings_fails_when_secrets_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_var in [
        "POSTGRES_PASSWORD",
        "DATABASE_URL",
        "TEST_DATABASE_URL",
        "REDIS_URL",
        "TEST_REDIS_URL",
        "JWT_SECRET_KEY",
        "S3_ACCESS_KEY_ID",
        "S3_SECRET_ACCESS_KEY",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "POSTGRES_HOST",
        "POSTGRES_USER",
        "POSTGRES_DB",
        "S3_ENDPOINT_URL",
        "S3_PUBLIC_BASE_URL",
        "STRIPE_SUCCESS_URL",
        "STRIPE_CANCEL_URL",
    ]:
        monkeypatch.delenv(env_var, raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_succeeds_with_valid_env() -> None:
    settings = Settings(
        POSTGRES_HOST="localhost",
        POSTGRES_USER="obsolete_user",
        POSTGRES_PASSWORD="test_password",
        POSTGRES_DB="obsolete_db",
        DATABASE_URL="postgresql+asyncpg://obsolete_user:test@localhost:5432/obsolete_db",
        TEST_DATABASE_URL="postgresql+asyncpg://obsolete_user:test@localhost:5432/obsolete_test_db",
        REDIS_URL="redis://localhost:6379/0",
        TEST_REDIS_URL="redis://localhost:6379/1",
        JWT_SECRET_KEY="test_jwt_secret_key_32_characters_minimum",
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_PUBLIC_BASE_URL="http://localhost:9000/obsolete-media",
        S3_ACCESS_KEY_ID="test_minio_user",
        S3_SECRET_ACCESS_KEY="test_minio_password",
        STRIPE_SECRET_KEY="sk_test_123",
        STRIPE_WEBHOOK_SECRET="whsec_123",
        STRIPE_SUCCESS_URL="http://localhost:5173/wallet?topup=success",
        STRIPE_CANCEL_URL="http://localhost:5173/wallet?topup=cancelled",
        _env_file=None,
    )
    assert settings.POSTGRES_USER == "obsolete_user"
    assert settings.database_url_str.startswith("postgresql+asyncpg://")
    assert settings.cors_origins == ["http://localhost:5173"]


def test_verify_no_comments_detects_comment(tmp_path: Path) -> None:
    bad_py = tmp_path / "bad_comment.py"
    bad_py.write_text("x = 1  # forbidden comment\n", encoding="utf-8")
    violations = check_python_file(bad_py)
    assert len(violations) == 1
    assert "forbidden Python comment" in violations[0]


def test_verify_no_comments_detects_docstring(tmp_path: Path) -> None:
    bad_py = tmp_path / "bad_docstring.py"
    bad_py.write_text("def sample():\n    '''forbidden doc'''\n    return 42\n", encoding="utf-8")
    violations = check_python_file(bad_py)
    assert len(violations) == 1
    assert "forbidden docstring" in violations[0]


def test_verify_no_comments_detects_pass(tmp_path: Path) -> None:
    bad_py = tmp_path / "bad_pass.py"
    bad_py.write_text("def sample():\n    pass\n", encoding="utf-8")
    violations = check_python_file(bad_py)
    assert len(violations) == 1
    assert "forbidden 'pass' statement" in violations[0]


def test_verify_no_comments_detects_not_implemented(tmp_path: Path) -> None:
    bad_py = tmp_path / "bad_not_implemented.py"
    bad_py.write_text("def sample():\n    raise NotImplementedError()\n", encoding="utf-8")
    violations = check_python_file(bad_py)
    assert len(violations) == 1
    assert "forbidden NotImplementedError" in violations[0]


def test_verify_no_comments_detects_frontend_violations(tmp_path: Path) -> None:
    bad_ts = tmp_path / "bad_component.tsx"
    bad_ts.write_text(
        "// forbidden comment\nconst x = 1; /* inline */\n// TODO: fix\n", encoding="utf-8"
    )
    violations = check_frontend_file(bad_ts)
    assert len(violations) >= 2


def test_git_ignores_instructions_and_env() -> None:
    git_bin = shutil.which("git")
    assert git_bin is not None
    proc_instructions = subprocess.run(
        [git_bin, "check-ignore", "instructions/tech.md"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_instructions.returncode == 0
    assert "instructions" in proc_instructions.stdout

    proc_env = subprocess.run(
        [git_bin, "check-ignore", ".env"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_env.returncode == 0
    assert ".env" in proc_env.stdout


def test_clock_and_domain_error_rfc7807() -> None:
    system_clock = SystemClock()
    now_utc = system_clock.now()
    assert now_utc.tzinfo is not None

    fixed_time = datetime(2026, 10, 24, 12, 0, 0, tzinfo=UTC)
    frozen_clock = FrozenClock(fixed_time)
    assert frozen_clock.now() == fixed_time

    advanced_time = datetime(2026, 10, 24, 12, 5, 0, tzinfo=UTC)
    frozen_clock.set_time(advanced_time)
    assert frozen_clock.now() == advanced_time

    error = DomainError(
        message="Insufficient funds",
        error_code="INSUFFICIENT_FUNDS",
        status_code=400,
        details={"balance": "10.00"},
    )
    problem = error.to_problem_details(server_time=advanced_time)
    assert problem["error_code"] == "INSUFFICIENT_FUNDS"
    assert problem["message"] == "Insufficient funds"
    assert problem["details"] == {"balance": "10.00"}
    assert problem["server_time"] == advanced_time.isoformat()

    not_found = NotFoundError()
    assert not_found.status_code == 404
    assert not_found.error_code == "NOT_FOUND"
