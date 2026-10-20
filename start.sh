#!/usr/bin/env bash
# Installs uv from its official site if missing; no sudo or system Python changes.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
UV="$(command -v uv || true)"
if [[ -z "$UV" && -x "$HOME/.local/bin/uv" ]]; then UV="$HOME/.local/bin/uv"; fi
if [[ -z "$UV" ]]; then
  printf '%s\n' 'Installing uv from https://astral.sh/uv/install.sh into your user account.'
  installer="$(mktemp)"
  trap 'rm -f "$installer"' EXIT
  if command -v curl >/dev/null 2>&1; then
    curl --proto '=https' --tlsv1.2 -fsSL https://astral.sh/uv/install.sh -o "$installer"
  elif command -v wget >/dev/null 2>&1; then
    wget -q https://astral.sh/uv/install.sh -O "$installer"
  else
    printf '%s\n' 'Install curl or wget, or install uv manually (see README).' >&2
    exit 1
  fi
  UV_NO_MODIFY_PATH=1 sh "$installer"
  UV="$HOME/.local/bin/uv"
  [[ -x "$UV" ]] || { echo 'uv not found after installation; check UV_INSTALL_DIR.' >&2; exit 1; }
  rm -f "$installer"
  trap - EXIT
fi
extras=()
args=()
command=ui
for arg in "$@"; do
  case "$arg" in
    --local) extras+=(--extra local) ;;
    --quantized) extras+=(--extra local --extra quantized) ;;
    --doctor) command=doctor ;;
    *) args+=("$arg") ;;
  esac
done
export GRADIO_ANALYTICS_ENABLED=False
export HF_HUB_DISABLE_TELEMETRY=1
cd "$ROOT"
exec "$UV" run --python 3.11 --project "$ROOT" "${extras[@]}" longbook "$command" "${args[@]}"
