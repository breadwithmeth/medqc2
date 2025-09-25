#!/usr/bin/env bash
set -euo pipefail
RULES="${1:-rules_all.yaml}"
OUT="${2:-Modelfile.stac.strict}"
BASE="${BASE:-llama3.1:8b-instruct-q5_1}"
NAME="${NAME:-medaudit:stac-strict}"
CTX="${CTX:-3072}"

echo "[i] Using: RULES=$RULES BASE=$BASE NAME=$NAME CTX=$CTX OUT=$OUT"

ollama pull "$BASE"

python3 tools/build_modelfile_single_profile.py "$OUT" "$RULES" \
  --base "$BASE" --name "$NAME" --num_ctx "$CTX" --include GEN STAC

# переcоздать модель (если уже была)
ollama rm "$NAME" 2>/dev/null || true
ollama create "$NAME" -f "$OUT"

echo "[✔] Model created: $NAME"
ollama show "$NAME" | head -n 40 || true
