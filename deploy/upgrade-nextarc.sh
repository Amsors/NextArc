#!/usr/bin/env bash
set -Eeuo pipefail

NEXTARC_INSTALL_DIR="${NEXTARC_INSTALL_DIR:-/opt/nextarc}"
NEXTARC_APP_DIR="${NEXTARC_APP_DIR:-/opt/nextarc/app}"
NEXTARC_PYUSTC_DIR="${NEXTARC_PYUSTC_DIR:-/opt/nextarc/pyustc}"
NEXTARC_VENV_DIR="${NEXTARC_VENV_DIR:-/opt/nextarc/venv}"
NEXTARC_CONFIG_DIR="${NEXTARC_CONFIG_DIR:-/etc/nextarc}"
NEXTARC_STATE_DIR="${NEXTARC_STATE_DIR:-/var/lib/nextarc}"
NEXTARC_LOG_DIR="${NEXTARC_LOG_DIR:-/var/log/nextarc}"

REQUEST_FILE="${NEXTARC_STATE_DIR}/upgrade-request.env"
STATUS_FILE="${NEXTARC_STATE_DIR}/upgrade-status.env"
MARKER_FILE="${NEXTARC_STATE_DIR}/.next_arc_updated"
LOCK_FILE="${NEXTARC_STATE_DIR}/upgrade.lock"

log() {
  echo "[$(date --iso-8601=seconds)] $*"
}

write_status() {
  local status="$1"
  local message="$2"
  python3 - "${STATUS_FILE}" "${status}" "${message}" <<'PY'
from pathlib import Path
import shlex
import sys
from datetime import datetime

path = Path(sys.argv[1])
status = sys.argv[2]
message = sys.argv[3]
path.write_text(
    "NEXTARC_UPGRADE_STATUS=" + shlex.quote(status) + "\n"
    "NEXTARC_UPGRADE_MESSAGE=" + shlex.quote(message) + "\n"
    "NEXTARC_UPGRADE_TIME=" + shlex.quote(datetime.now().isoformat(timespec="seconds")) + "\n",
    encoding="utf-8",
)
path.chmod(0o600)
PY
}

start_nextarc() {
  systemctl start nextarc || true
}

fail() {
  local message="$1"
  log "升级失败: ${message}"
  write_status "failed" "${message}"
  start_nextarc
  exit 1
}

validate_ref() {
  local value="$1"
  [[ -n "${value}" ]] || return 1
  [[ "${value}" != -* ]] || return 1
  [[ "${value}" != *..* ]] || return 1
  [[ "${value}" != *.lock ]] || return 1
  [[ "${value}" =~ ^[A-Za-z0-9._/-]+$ ]]
}

validate_remote() {
  local value="$1"
  [[ -n "${value}" ]] || return 1
  [[ "${value}" =~ ^[A-Za-z0-9._-]+$ ]]
}

main() {
  exec 9>"${LOCK_FILE}"
  flock -n 9 || fail "已有升级任务正在运行"

  [[ -f "${REQUEST_FILE}" ]] || fail "升级请求文件不存在: ${REQUEST_FILE}"
  # shellcheck disable=SC1090
  source "${REQUEST_FILE}"

  local remote="${NEXTARC_UPGRADE_REMOTE:-origin}"
  local branch="${NEXTARC_UPGRADE_BRANCH:-main}"
  local old_version="${NEXTARC_OLD_VERSION:-}"

  validate_remote "${remote}" || fail "远程仓库名称不安全: ${remote}"
  validate_ref "${branch}" || fail "分支名称不安全: ${branch}"
  [[ -d "${NEXTARC_APP_DIR}/.git" ]] || fail "NextArc 目录不是 git 仓库: ${NEXTARC_APP_DIR}"
  [[ -d "${NEXTARC_PYUSTC_DIR}/.git" ]] || fail "pyustc 目录不是 git 仓库: ${NEXTARC_PYUSTC_DIR}"
  [[ -x "${NEXTARC_VENV_DIR}/bin/pip" ]] || fail "虚拟环境不可用: ${NEXTARC_VENV_DIR}"

  write_status "running" "正在升级到 ${remote}/${branch}"
  log "停止 nextarc 服务"
  systemctl stop nextarc || true

  log "更新 NextArc: ${remote}/${branch}"
  git -C "${NEXTARC_APP_DIR}" fetch "${remote}" "${branch}" || fail "NextArc fetch 失败"
  if git -C "${NEXTARC_APP_DIR}" show-ref --verify --quiet "refs/heads/${branch}"; then
    git -C "${NEXTARC_APP_DIR}" switch "${branch}" || fail "切换 NextArc 分支失败"
  else
    git -C "${NEXTARC_APP_DIR}" switch --track -c "${branch}" "${remote}/${branch}" || fail "创建 NextArc 跟踪分支失败"
  fi
  git -C "${NEXTARC_APP_DIR}" pull --ff-only "${remote}" "${branch}" || fail "NextArc pull 失败"

  log "更新 pyustc"
  git -C "${NEXTARC_PYUSTC_DIR}" pull --ff-only || fail "pyustc pull 失败"

  log "在虚拟环境中安装 NextArc 依赖"
  "${NEXTARC_VENV_DIR}/bin/pip" install -r "${NEXTARC_APP_DIR}/requirements.txt" || fail "安装 NextArc 依赖失败"

  log "在虚拟环境中安装 pyustc"
  "${NEXTARC_VENV_DIR}/bin/pip" install -e "${NEXTARC_PYUSTC_DIR}" || fail "安装 pyustc 失败"

  log "修正权限"
  chown -R root:root "${NEXTARC_INSTALL_DIR}"
  chown -R root:nextarc "${NEXTARC_CONFIG_DIR}"
  chown -R nextarc:nextarc "${NEXTARC_STATE_DIR}" "${NEXTARC_LOG_DIR}"
  chmod 750 "${NEXTARC_CONFIG_DIR}" "${NEXTARC_STATE_DIR}" "${NEXTARC_LOG_DIR}"

  printf '%s\n' "${old_version}" >"${MARKER_FILE}"
  chown nextarc:nextarc "${MARKER_FILE}"
  chmod 600 "${MARKER_FILE}"
  rm -f "${REQUEST_FILE}"

  write_status "succeeded" "升级完成"
  log "启动 nextarc 服务"
  systemctl start nextarc
  log "升级完成"
}

main "$@"
