from pathlib import Path


ENV_KEY_BY_SETTING = {
    "google_client_id": "GOOGLE_CLIENT_ID",
    "google_client_secret": "GOOGLE_CLIENT_SECRET",
    "openai_api_key": "OPENAI_API_KEY",
    "openrouter_api_key": "OPENROUTER_API_KEY",
    "default_summary_provider": "DEFAULT_SUMMARY_PROVIDER",
    "default_summary_model": "DEFAULT_SUMMARY_MODEL",
    "default_embedding_provider": "DEFAULT_EMBEDDING_PROVIDER",
    "default_embedding_model": "DEFAULT_EMBEDDING_MODEL",
}


def env_path() -> Path:
    return Path(".env")


def _format_env_value(value: str) -> str:
    if value == "":
        return ""
    if any(char.isspace() for char in value) or "#" in value or '"' in value:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def update_env_values(values: dict[str, str]) -> None:
    path = env_path()
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(values)
    updated_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            updated_lines.append(line)
            continue

        key = line.split("=", 1)[0].strip()
        if key in remaining:
            updated_lines.append(f"{key}={_format_env_value(remaining.pop(key) or '')}")
        else:
            updated_lines.append(line)

    for key, value in remaining.items():
        updated_lines.append(f"{key}={_format_env_value(value or '')}")

    path.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")
