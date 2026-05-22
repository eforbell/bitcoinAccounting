#!/usr/bin/env bash
# deploy.sh — git-based deploy for bitcoinAccounting web service on numenor
# Usage:
#   ./deploy/deploy.sh                   # deploy origin/main
#   ./deploy/deploy.sh feature/my-branch # deploy a specific ref
#   ./deploy/deploy.sh --restore-stash   # restore last auto-stashed local changes

set -euo pipefail

APP_DIR="/data/apps/bitcoinAccounting"
SERVICE="bitcoin-accounting-web"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REF="${1:-origin/main}"

if [[ -d "$APP_DIR/.git" ]]; then
  GIT_CMD=(git -C "$APP_DIR")
  STASH_REF_FILE="$APP_DIR/.deploy-last-stash-ref"
  MODE="repo"
else
  GIT_CMD=(git --git-dir="$REPO_DIR/.git" --work-tree="$APP_DIR")
  STASH_REF_FILE="$REPO_DIR/.deploy-last-stash-ref"
  MODE="worktree"
fi

restore_stash() {
  local stash_ref="${1:-}"
  if [[ -z "$stash_ref" ]]; then
    if [[ -f "$STASH_REF_FILE" ]]; then
      stash_ref="$(cat "$STASH_REF_FILE")"
    else
      echo "ERROR: No saved stash ref found."
      exit 1
    fi
  fi
  echo "==> Restoring stash: $stash_ref"
  "${GIT_CMD[@]}" stash pop "$stash_ref"
  rm -f "$STASH_REF_FILE"
  echo "==> Local changes restored."
}

if [[ "$REF" == "--restore-stash" ]]; then
  restore_stash "${2:-}"
  exit 0
fi

AUTO_STASH="${AUTO_STASH:-1}"

echo "==> bitcoinAccounting deploy: $REF"

if [[ -z "${FORCE_DEPLOY:-}" ]]; then
  if [[ -n "$("${GIT_CMD[@]}" status --porcelain)" ]]; then
    if [[ "$AUTO_STASH" == "1" ]]; then
      stamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      stash_msg="deploy:auto-stash:${stamp}:${REF}"
      echo "==> Local changes detected; auto-stashing before deploy"
      "${GIT_CMD[@]}" stash push --include-untracked -m "$stash_msg" >/dev/null
      stash_ref="$("${GIT_CMD[@]}" rev-parse -q --verify refs/stash || true)"
      if [[ -n "$stash_ref" ]]; then
        echo "$stash_ref" > "$STASH_REF_FILE"
        echo "==> Saved stash ref: $stash_ref"
        echo "==> Restore later with: ./deploy/deploy.sh --restore-stash"
      fi
    else
      echo "ERROR: Uncommitted local changes. Commit/stash first, or set AUTO_STASH=1."
      exit 1
    fi
  fi
fi

"${GIT_CMD[@]}" fetch origin --prune

TARGET="$REF"
if [[ "$REF" != origin/* ]] && "${GIT_CMD[@]}" show-ref --verify --quiet "refs/remotes/origin/$REF"; then
  TARGET="origin/$REF"
fi

echo "==> Updating work tree to $TARGET"
if [[ "$MODE" == "repo" ]]; then
  "${GIT_CMD[@]}" checkout -B deploy-current "$TARGET"
  "${GIT_CMD[@]}" reset --hard "$TARGET"
else
  "${GIT_CMD[@]}" checkout "$TARGET" -- .
fi

cd "$APP_DIR"

echo "==> Syncing Python environment"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .

echo "==> Validating runtime and initializing web-owned tables"
.venv/bin/bitcoin-accounting-web-init

echo "==> Restarting $SERVICE"
sudo systemctl restart "$SERVICE"
sudo systemctl status "$SERVICE" --no-pager -l

echo "==> Done."
