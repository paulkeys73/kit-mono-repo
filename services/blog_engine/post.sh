#!/usr/bin/env bash
set -uo pipefail

# ------------------------------
# Orchestrator: full blog pipeline for one topic
# Usage: bash post.sh "your topic"
# ------------------------------

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRAPERS_DIR="$BASE_DIR/app/services/externals/Scrapers"
SERVICES_DIR="$BASE_DIR/app/services"
OUTPUT_FILE="$SERVICES_DIR/data/outputs/blog_posts.json"
TOPIC="${*:-What are the advantages and disadvantages of artificial intelligence}"

if [ -x "$BASE_DIR/venv/bin/python" ]; then
  PYTHON_BIN="$BASE_DIR/venv/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
  if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    PYTHON_BIN="python"
  fi
fi

run_step() {
  local step_name="$1"
  shift
  echo "Running ${step_name}..."
  if "$@"; then
    echo "${step_name} finished."
  else
    local exit_code=$?
    echo "${step_name} failed with exit code ${exit_code}."
    FAILED_STEPS+=("${step_name} (exit ${exit_code})")
  fi
}

echo "Topic: $TOPIC"
FAILED_STEPS=()

# ------------------------------
# 1) Run Wikipedia scraper
# ------------------------------
cd "$SCRAPERS_DIR" || exit 1
run_step "wikipedia_scraper.py" "$PYTHON_BIN" wikipedia_scraper.py "$TOPIC"
sleep 2

# ------------------------------
# 2) Run competitor scraper
# ------------------------------
run_step "competitor_scraper.py" "$PYTHON_BIN" competitor_scraper.py
sleep 2

# ------------------------------
# 3) Extract keywords
# ------------------------------
run_step "keywords.py" "$PYTHON_BIN" "$SERVICES_DIR/keywords.py"

# ------------------------------
# 4) Build blog JSON from scraped content
# ------------------------------
cd "$SERVICES_DIR" || exit 1
run_step "generation.py" "$PYTHON_BIN" generation.py

# ------------------------------
# 5) Build final SEO JSON + images
# ------------------------------
cd "$BASE_DIR" || exit 1
run_step "app.services.blog_content" "$PYTHON_BIN" -m app.services.blog_content

# ------------------------------
# 6) Publish to WordPress (disabled by default)
# ------------------------------
if [ "${ENABLE_WP_POST:-0}" = "1" ]; then
  run_step "wp_post.py" "$PYTHON_BIN" "$SERVICES_DIR/wp_post.py"
else
  echo "Skipping wp_post.py (set ENABLE_WP_POST=1 to enable)."
fi

# ------------------------------
# 7) Submit URLs to Bing (disabled by default)
# ------------------------------
if [ "${ENABLE_BING_NOTIFY:-0}" = "1" ]; then
  run_step "bing_notify.py" "$PYTHON_BIN" "$SERVICES_DIR/bing_notify.py"
else
  echo "Skipping bing_notify.py (set ENABLE_BING_NOTIFY=1 to enable)."
fi

# ------------------------------
# 8) Update remote sitemap (disabled by default)
# ------------------------------
if [ "${ENABLE_SITEMAP_UPDATE:-0}" = "1" ]; then
  if command -v sshpass >/dev/null 2>&1 && [ -f "$OUTPUT_FILE" ]; then
    mapfile -t POST_URLS < <(
      "$PYTHON_BIN" - <<PY
import json
from pathlib import Path

file_path = Path(r"$OUTPUT_FILE")
with file_path.open("r", encoding="utf-8") as f:
    posts = json.load(f)

for post in posts.values():
    slug = str(post.get("slug", "")).strip()
    if slug:
        print(f"https://seo-post.paycc.store/{slug}")
PY
    )

    if [ "${#POST_URLS[@]}" -gt 0 ]; then
      run_step "update_sitemap.sh" bash "$BASE_DIR/update_sitemap.sh" "${POST_URLS[@]}"
    else
      echo "Skipping update_sitemap.sh: no post URLs found."
    fi
  else
    echo "Skipping update_sitemap.sh: missing sshpass or output file."
  fi
else
  echo "Skipping update_sitemap.sh (set ENABLE_SITEMAP_UPDATE=1 to enable)."
fi

if [ "${#FAILED_STEPS[@]}" -gt 0 ]; then
  echo "Pipeline completed with failures for topic: $TOPIC"
  printf 'Failed steps:\n'
  printf ' - %s\n' "${FAILED_STEPS[@]}"
  exit 1
fi

echo "Full pipeline completed for topic: $TOPIC"
