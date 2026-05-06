import os
from dataclasses import dataclass
from pathlib import Path


def _iter_env_paths() -> list[Path]:
    project_root = Path(__file__).resolve().parents[3]
    return [
        project_root / ".env",
    ]


def _strip_inline_comment(value: str) -> str:
    in_single_quote = False
    in_double_quote = False

    for index, char in enumerate(value):
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif char == "#" and not in_single_quote and not in_double_quote:
            if index == 0 or value[index - 1].isspace():
                return value[:index].rstrip()
    return value.strip()


def _parse_env_value(value: str) -> str:
    stripped = _strip_inline_comment(value)
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()
        if key and key not in os.environ:
            os.environ[key] = _parse_env_value(value)


for env_path in _iter_env_paths():
    _load_env_file(env_path)


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Autonomous Job Application Agent")
    min_apply_score: int = int(os.getenv("MIN_APPLY_SCORE", "75"))
    min_review_score: int = int(os.getenv("MIN_REVIEW_SCORE", "50"))
    database_path: Path = Path(os.getenv("DATABASE_PATH", "data/agent.db"))
    serpapi_api_key: str = os.getenv("SERPAPI_API_KEY", "")


settings = Settings()
