#!/usr/bin/env bash
# Model prices and task routes (stored in the database). Idempotent: re-running updates them.
# Text tasks run on Groq (cheap); photo understanding needs a vision model (OpenAI).
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE=(docker compose --env-file .env -f infra/compose/compose.yml -f infra/compose/compose.prod.yml)
cli() { "${COMPOSE[@]}" exec -T api python -m stylesense.cli "$@" >/dev/null; }

GROQ=groq:openai/gpt-oss-20b
VISION=openai:gpt-5.4-mini

# USD per million tokens (input, cached input, output)
cli llm-price "$GROQ" --input 0.075 --cached 0.075 --output 0.30
cli llm-price "$VISION" --input 0.75 --cached 0.075 --output 4.50

# task, model, max output tokens, timeout (s), answer cache (s)
cli llm-route stylist.understand "$GROQ" --max-output 400 --timeout 12 --cache-ttl 86400
cli llm-route stylist.explain "$GROQ" --max-output 400 --timeout 12 --cache-ttl 86400
cli llm-route stylist.advise "$GROQ" --max-output 400 --timeout 12 --cache-ttl 86400
cli llm-route look.complete "$GROQ" --max-output 500 --timeout 15 --cache-ttl 86400
cli llm-route diagnostics.echo "$GROQ" --max-output 200 --timeout 12
cli llm-route photo.understand "$VISION" --max-output 800 --timeout 25

echo "AI routes set: text → $GROQ, photos → $VISION"
