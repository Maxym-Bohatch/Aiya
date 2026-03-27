import secrets
from pathlib import Path


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def save_env_file(path: Path, values: dict[str, str]):
    lines = [f"{key}={values.get(key, '')}" for key in sorted(values)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_defaults(values: dict[str, str], defaults: dict[str, str]) -> dict[str, str]:
    merged = dict(defaults)
    merged.update({key: value for key, value in values.items() if value is not None})
    return merged


def generate_secure_token(length_bytes: int = 24) -> str:
    return secrets.token_urlsafe(length_bytes)
