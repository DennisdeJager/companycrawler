#!/usr/bin/env sh
set -eu

target_env="$1"
legacy_env="${2:-}"
example_env="${3:-}"

target_dir="$(dirname "$target_env")"
mkdir -p "$target_dir"

if [ ! -f "$target_env" ] && [ -n "$legacy_env" ] && [ -f "$legacy_env" ]; then
  cp "$legacy_env" "$target_env"
  exit 0
fi

if [ ! -f "$target_env" ] && [ -n "$example_env" ] && [ -f "$example_env" ]; then
  cp "$example_env" "$target_env"
fi

[ -n "$legacy_env" ] && [ -f "$legacy_env" ] || exit 0
touch "$target_env"

for key in GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET APP_URL OPENAI_API_KEY OPENROUTER_API_KEY; do
  target_line="$(grep -E "^${key}=.+" "$target_env" | tail -n 1 || true)"
  legacy_line="$(grep -E "^${key}=.+" "$legacy_env" | tail -n 1 || true)"

  [ -z "$target_line" ] || continue
  [ -n "$legacy_line" ] || continue

  if grep -qE "^${key}=" "$target_env"; then
    tmp_file="${target_env}.tmp.$$"
    awk -v key="$key" -v line="$legacy_line" '
      BEGIN { replaced = 0 }
      $0 ~ "^" key "=" {
        if (!replaced) {
          print line
          replaced = 1
        }
        next
      }
      { print }
      END {
        if (!replaced) {
          print line
        }
      }
    ' "$target_env" > "$tmp_file"
    mv "$tmp_file" "$target_env"
  else
    printf '%s\n' "$legacy_line" >> "$target_env"
  fi
done
