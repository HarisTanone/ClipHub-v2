#!/usr/bin/env bash
# Pre-deployment test gate for ClipHub.
# Usage: ./test.sh [--no-deploy]

set -Eeuo pipefail

# systemd/non-login shells often omit common Node.js installation paths.
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH}"
if [[ -s "${HOME:-}/.nvm/nvm.sh" ]]; then
  # shellcheck source=/dev/null
  source "${HOME}/.nvm/nvm.sh"
fi

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs"
LOG_FILE="${LOG_DIR}/test.log"
STATUS_FILE="${LOG_DIR}/test-status.json"
LOCK_DIR="${LOG_DIR}/test.lock"
INPUT_VIDEO="${PROJECT_ROOT}/clip_01.mp4"
OUTPUT_VIDEO="${PROJECT_ROOT}/clip_test_final.mp4"
TMP_OUTPUT_VIDEO="${OUTPUT_VIDEO}.tmp.mp4"
DEPLOY_AFTER_TESTS=true
CURRENT_STAGE="initializing"

if [[ "${1:-}" == "--no-deploy" ]]; then
  DEPLOY_AFTER_TESTS=false
elif [[ $# -gt 0 ]]; then
  printf 'Usage: %s [--no-deploy]\n' "$0" >&2
  exit 2
fi

mkdir -p "${LOG_DIR}"
if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  LOCK_PID="$(cat "${LOCK_DIR}/pid" 2>/dev/null || true)"
  if [[ -n "${LOCK_PID}" ]] && kill -0 "${LOCK_PID}" 2>/dev/null; then
    printf 'A test run is already active (PID %s). See %s\n' "${LOCK_PID}" "${LOG_FILE}" >&2
    exit 3
  fi
  rm -rf "${LOCK_DIR}"
  mkdir "${LOCK_DIR}"
fi
printf '%s\n' "$$" > "${LOCK_DIR}/pid"

: > "${LOG_FILE}"
exec > >(tee -a "${LOG_FILE}") 2>&1

write_status() {
  local status="$1" stage="$2" message="$3"
  local video_available=false deploy_requested=false
  [[ -s "${OUTPUT_VIDEO}" ]] && video_available=true
  [[ "${DEPLOY_AFTER_TESTS}" == true ]] && deploy_requested=true
  local tmp_status="${STATUS_FILE}.tmp"
  printf '{"status":"%s","stage":"%s","message":"%s","pid":%s,"updated_at":"%s","log_available":true,"video_available":%s,"deploy_requested":%s}\n' \
    "${status}" "${stage}" "${message}" "$$" "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
    "${video_available}" "${deploy_requested}" > "${tmp_status}"
  mv "${tmp_status}" "${STATUS_FILE}"
}

cleanup() {
  rm -f "${TMP_OUTPUT_VIDEO}"
  rm -rf "${LOCK_DIR}"
}

on_error() {
  local exit_code=$? line_number="${BASH_LINENO[0]:-unknown}"
  trap - ERR
  printf '\n[FAIL] Stage "%s" failed at line %s (exit code %s).\n' "${CURRENT_STAGE}" "${line_number}" "${exit_code}"
  printf '[FAIL] Full testing log: %s\n' "${LOG_FILE}"
  write_status "failed" "${CURRENT_STAGE}" "Test failed; inspect the log"
  exit "${exit_code}"
}

trap cleanup EXIT
trap on_error ERR

run_stage() {
  CURRENT_STAGE="$1"
  shift
  write_status "running" "${CURRENT_STAGE}" "Running ${CURRENT_STAGE}"
  printf '\n%s\n[TEST] %s\n%s\n' '======================================================================' "${CURRENT_STAGE}" '======================================================================'
  "$@"
  printf '[PASS] %s\n' "${CURRENT_STAGE}"
}

BACKEND_DIR="${PROJECT_ROOT}/backend"
BACKEND_VENV="${BACKEND_DIR}/venv"
PYTHON_BIN="${BACKEND_VENV}/bin/python"
PIP_BIN="${BACKEND_VENV}/bin/pip"
DEV_REQUIREMENTS="${BACKEND_DIR}/requirements-dev.txt"

printf 'ClipHub pre-deployment test gate\nStarted: %s\nProject: %s\nLog: %s\n' \
  "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "${PROJECT_ROOT}" "${LOG_FILE}"
write_status "running" "initializing" "Validating server test environment"

CURRENT_STAGE="environment validation"
[[ -x "${PYTHON_BIN}" ]] || {
  echo "[ERROR] Backend virtualenv Python was not found: ${PYTHON_BIN}"
  echo "[ERROR] Run deploy.sh once or create backend/venv and install backend requirements."
  false
}
[[ -x "${PIP_BIN}" ]] || { echo "[ERROR] Backend virtualenv pip was not found: ${PIP_BIN}"; false; }
[[ -f "${DEV_REQUIREMENTS}" ]] || { echo "[ERROR] Test dependencies file is missing: ${DEV_REQUIREMENTS}"; false; }
command -v npm >/dev/null || { echo '[ERROR] npm was not found'; false; }
command -v ffmpeg >/dev/null || { echo '[ERROR] ffmpeg was not found'; false; }
command -v ffprobe >/dev/null || { echo '[ERROR] ffprobe was not found'; false; }
[[ -f "${INPUT_VIDEO}" ]] || { echo "[ERROR] Production test input is missing: ${INPUT_VIDEO}"; false; }
[[ -f "${PROJECT_ROOT}/deploy.sh" ]] || { echo "[ERROR] deploy.sh is missing: ${PROJECT_ROOT}/deploy.sh"; false; }
[[ -d "${PROJECT_ROOT}/frontend/node_modules" ]] || { echo '[ERROR] frontend dependencies are missing; run npm ci'; false; }
[[ -d "${PROJECT_ROOT}/remotion-renderer/node_modules" ]] || { echo '[ERROR] Remotion dependencies are missing; run npm ci'; false; }

printf 'Backend Python: %s\n' "${PYTHON_BIN}"
printf 'Backend Python version: %s\n' "$("${PYTHON_BIN}" --version 2>&1)"
if ! "${PYTHON_BIN}" -c 'import pytest, pytest_asyncio' >/dev/null 2>&1; then
  CURRENT_STAGE="test dependency installation"
  write_status "running" "${CURRENT_STAGE}" "Installing backend test dependencies"
  printf '[SETUP] Backend test dependencies are incomplete; installing %s into backend/venv\n' "${DEV_REQUIREMENTS}"
  "${PIP_BIN}" install -r "${DEV_REQUIREMENTS}"
fi
printf 'Pytest version: %s\n' "$("${PYTHON_BIN}" -m pytest --version)"

run_stage "Backend test suite" bash -c 'cd "$1" && "$2" -m pytest -v --tb=short tests' _ "${BACKEND_DIR}" "${PYTHON_BIN}"
run_stage "Frontend test suite" npm --prefix "${PROJECT_ROOT}/frontend" test
run_stage "Frontend production build" npm --prefix "${PROJECT_ROOT}/frontend" run build
run_stage "Remotion test suite" npm --prefix "${PROJECT_ROOT}/remotion-renderer" test
run_stage "Remotion TypeScript build" npm --prefix "${PROJECT_ROOT}/remotion-renderer" run build

CURRENT_STAGE="Production video smoke test"
write_status "running" "${CURRENT_STAGE}" "Rendering clip_01.mp4"
printf '\n%s\n[TEST] %s\n%s\n' '======================================================================' "${CURRENT_STAGE}" '======================================================================'
rm -f "${TMP_OUTPUT_VIDEO}"
ffmpeg -hide_banner -y -i "${INPUT_VIDEO}" -t 10 \
  -vf "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:black,drawbox=x=0:y=h-150:w=w:h=150:color=black@0.55:t=fill,drawtext=text='CLIPHUB TEST PASS':fontcolor=white:fontsize=36:x=(w-text_w)/2:y=h-95" \
  -c:v libx264 -preset fast -crf 23 -c:a aac -b:a 128k -movflags +faststart "${TMP_OUTPUT_VIDEO}"
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height \
  -show_entries format=duration -of json "${TMP_OUTPUT_VIDEO}"
[[ -s "${TMP_OUTPUT_VIDEO}" ]] || { echo '[ERROR] Smoke-test output is empty'; false; }
mv "${TMP_OUTPUT_VIDEO}" "${OUTPUT_VIDEO}"
printf '[PASS] Production video smoke test: %s\n' "${OUTPUT_VIDEO}"

if [[ "${DEPLOY_AFTER_TESTS}" == true ]]; then
  CURRENT_STAGE="deployment"
  write_status "deploying" "${CURRENT_STAGE}" "All tests passed; deploy.sh is running"
  printf '\n[PASS] ALL TESTS PASSED — starting deploy.sh\n'
  bash "${PROJECT_ROOT}/deploy.sh"
  write_status "passed" "completed" "All tests passed and deployment completed"
  printf '\n[SUCCESS] All tests passed and deployment completed.\n'
else
  write_status "passed" "completed" "All tests passed; deployment was not requested"
  printf '\n[SUCCESS] All tests passed. Deployment skipped (--no-deploy).\n'
fi

printf 'Testing log: %s\nPreview video: %s\n' "${LOG_FILE}" "${OUTPUT_VIDEO}"