#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

fail() {
  echo "security check failed: $1" >&2
  exit 1
}

if rg -n --pcre2 '(?<![\w.])(eval|exec|compile)\s*\(|\bos\.system\s*\(' backend/app frontend/src; then
  fail "runtime source contains a dynamic code execution call"
fi

if rg -n --pcre2 '(^|\s)(from|import)\s+(subprocess|pty|code|codeop)(\s|\.|$)' backend/app; then
  fail "backend imports a process or interpreter module"
fi

if rg -n --pcre2 'node:(child_process|vm|worker_threads)|new\s+Function\s*\(' frontend/src; then
  fail "frontend runtime contains a process or dynamic execution capability"
fi

if rg -n 'PythonExecute|BrowserUseTool|StrReplaceEditor|browser-use|crawl4ai' backend/app frontend/src; then
  fail "runtime source contains a forbidden agent, browser or file tool"
fi

if rg -n --pcre2 '\b(write_text|write_bytes)\s*\(' backend/app; then
  fail "backend runtime writes files"
fi

if rg -n '^[[:space:]]*"(browser-use|crawl4ai|playwright|patchright|@playwright/test)([<>=~^":,]|$)' backend/pyproject.toml frontend/package.json; then
  fail "a browser automation package is declared"
fi

installed_frontend=$(cd frontend && npm ls --all --parseable 2>/dev/null || true)
if printf '%s\n' "$installed_frontend" | rg '/node_modules/(@playwright/test|playwright|patchright)$'; then
  fail "a browser automation package is installed"
fi

git check-ignore -q .env || fail ".env is not ignored"
if git ls-files refer | rg -q .; then
  fail "refer/ must never be tracked"
fi
if git ls-files .env .claude/settings.local.json .agents .codex | rg -q .; then
  fail "a local-only configuration path is tracked"
fi
if find docs -maxdepth 1 -type f \
  \( -name '*_AUDIT.md' -o -name '*_ACCEPTANCE.md' -o -name '*_PHASE.md' -o -name '*_MATRIX.md' \) |
  rg -q .; then
  fail "an internal planning or audit document is present"
fi

while IFS= read -r asset; do
  rg -Fq "$asset" ASSETS.md || fail "$asset is missing from ASSETS.md"
done < <(find frontend/public -type f | sort)

for asset in frontend/public/avatars/default.vrm docs/demo.mp4; do
  digest=$(shasum -a 256 "$asset" | awk '{print $1}')
  rg -Fq "$digest" ASSETS.md || fail "$asset hash does not match ASSETS.md"
done

echo "security check passed"
