#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

fail() {
  echo "security check failed: $1" >&2
  exit 1
}

if grep -r -I -n -E \
  '(^|[^[:alnum:]_.])(eval|exec|compile)[[:space:]]*\(|(^|[^[:alnum:]_])os\.system[[:space:]]*\(' \
  backend/app frontend/src; then
  fail "runtime source contains a dynamic code execution call"
fi

if grep -r -I -n -E \
  '(^|[[:space:]])(from|import)[[:space:]]+(subprocess|pty|code|codeop)([[:space:].]|$)' \
  backend/app; then
  fail "backend imports a process or interpreter module"
fi

if grep -r -I -n -E \
  'node:(child_process|vm|worker_threads)|new[[:space:]]+Function[[:space:]]*\(' \
  frontend/src; then
  fail "frontend runtime contains a process or dynamic execution capability"
fi

if grep -r -I -n -E \
  'PythonExecute|BrowserUseTool|StrReplaceEditor|browser-use|crawl4ai' \
  backend/app frontend/src; then
  fail "runtime source contains a forbidden agent, browser or file tool"
fi

if grep -r -I -n -E \
  '(^|[^[:alnum:]_])(write_text|write_bytes)[[:space:]]*\(' \
  backend/app; then
  fail "backend runtime writes files"
fi

if grep -n -E \
  '^[[:space:]]*"(browser-use|crawl4ai|playwright|patchright|@playwright/test)([<>=~^":,]|$)' \
  backend/pyproject.toml frontend/package.json; then
  fail "a browser automation package is declared"
fi

installed_frontend=$(cd frontend && npm ls --all --parseable 2>/dev/null || true)
if grep -q -E '/node_modules/(@playwright/test|playwright|patchright)$' \
  <<<"$installed_frontend"; then
  fail "a browser automation package is installed"
fi

git check-ignore -q .env || fail ".env is not ignored"
tracked_refer=$(git ls-files -- refer)
if [[ -n "$tracked_refer" ]]; then
  fail "refer/ must never be tracked"
fi
tracked_local_config=$(git ls-files -- .env .claude/settings.local.json .agents .codex)
if [[ -n "$tracked_local_config" ]]; then
  fail "a local-only configuration path is tracked"
fi
internal_docs=$(
  find docs -maxdepth 1 -type f \
    \( -name '*_AUDIT.md' -o -name '*_ACCEPTANCE.md' -o -name '*_PHASE.md' -o -name '*_MATRIX.md' \)
)
if [[ -n "$internal_docs" ]]; then
  fail "an internal planning or audit document is present"
fi

while IFS= read -r asset; do
  grep -Fq -- "$asset" ASSETS.md || fail "$asset is missing from ASSETS.md"
done < <(find frontend/public -type f | sort)

for asset in frontend/public/avatars/default.vrm docs/demo.mp4; do
  digest=$(shasum -a 256 "$asset" | awk '{print $1}')
  grep -Fq -- "$digest" ASSETS.md || fail "$asset hash does not match ASSETS.md"
done

echo "security check passed"
