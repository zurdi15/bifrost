#!/usr/bin/env bash
# Design-token guard: the token source and generated CSS are the only places
# raw design values may live. Fails CI on violations.
set -euo pipefail
cd "$(dirname "$0")/.."

fail=0

check() {
  local label="$1" pattern="$2"
  shift 2
  # Remaining args are passed to rg (globs etc.)
  if rg --line-number --no-heading "$pattern" src "$@" \
    --glob '!src/tokens/**' --glob '!src/styles/tokens.css'; then
    echo "✗ guard:tokens — $label" >&2
    fail=1
  fi
}

# Hex colors belong in src/tokens/index.ts only.
check "raw hex color outside tokens" '#[0-9a-fA-F]{3,8}\b' \
  --glob '!**/*.stories.ts' --glob '!**/*.test.ts' --glob '!**/*.svg'

# Easings are tokens (--bf-ease-*), not inline curves.
check "raw cubic-bezier outside tokens" 'cubic-bezier'

# Type scale comes from Tailwind/theme, not arbitrary pixel utilities.
check "arbitrary text size utility" 'text-\[[0-9]+px\]'

# The aurora is quirúrgica: only the design system and the app shell may use it.
if rg --line-number --no-heading 'var\(--bf-aurora\)' src \
  --glob '!src/lib/**' --glob '!src/layouts/**' --glob '!src/styles/**' \
  --glob '!src/tokens/**'; then
  echo "✗ guard:tokens — var(--bf-aurora) outside src/lib|layouts|styles" >&2
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "✓ guard:tokens clean"
fi
exit "$fail"
