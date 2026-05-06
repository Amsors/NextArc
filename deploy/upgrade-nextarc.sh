#!/usr/bin/env bash
set -Eeuo pipefail

NEXTARC_USER="${NEXTARC_USER:-nextarc}"
NEXTARC_INSTALL_DIR="${NEXTARC_INSTALL_DIR:-/opt/nextarc}"
NEXTARC_APP_DIR="${NEXTARC_APP_DIR:-/opt/nextarc/app}"
NEXTARC_PYUSTC_DIR="${NEXTARC_PYUSTC_DIR:-/opt/nextarc/pyustc}"
NEXTARC_VENV_DIR="${NEXTARC_VENV_DIR:-/opt/nextarc/venv}"
NEXTARC_CONFIG_DIR="${NEXTARC_CONFIG_DIR:-/etc/nextarc}"
NEXTARC_STATE_DIR="${NEXTARC_STATE_DIR:-/var/lib/nextarc}"
NEXTARC_LOG_DIR="${NEXTARC_LOG_DIR:-/var/log/nextarc}"
NEXTARC_ENV_FILE="${NEXTARC_ENV_FILE:-/etc/nextarc/nextarc.env}"

REQUEST_FILE="${NEXTARC_STATE_DIR}/upgrade-request.env"
STATUS_FILE="${NEXTARC_STATE_DIR}/upgrade-status.env"
MARKER_FILE="${NEXTARC_STATE_DIR}/.next_arc_updated"
LOCK_FILE="${NEXTARC_STATE_DIR}/upgrade.lock"

PATHS_VALIDATED="false"
BUILD_OWNERSHIP_GRANTED="false"

log() {
  echo "[$(date --iso-8601=seconds)] $*"
}

strip_trailing_slash() {
  local path="$1"
  while [[ "${path}" != "/" && "${path}" == */ ]]; do
    path="${path%/}"
  done
  printf '%s\n' "${path}"
}

fail_raw() {
  echo "升级失败: $*" >&2
  systemctl stop nextarc >/dev/null 2>&1 || true
  exit 1
}

validate_path_value() {
  local name="$1"
  local value
  value="$(strip_trailing_slash "$2")"

  [[ -n "${value}" ]] || fail_raw "${name} 不能为空"
  [[ "${value}" == /* ]] || fail_raw "${name} 必须是绝对路径: ${value}"
  case "/${value#/}/" in
    */../*|*/./*)
      fail_raw "${name} 不能包含 . 或 .. 路径组件: ${value}"
      ;;
  esac
  [[ ! -L "${value}" ]] || fail_raw "${name} 不能是符号链接: ${value}"

  case "${value}" in
    *$'\n'*|*$'\r'*|*[[:space:]]*)
      fail_raw "${name} 不能包含空白字符: ${value}"
      ;;
  esac

  case "${value}" in
    /|/bin|/boot|/dev|/etc|/home|/lib|/lib64|/opt|/proc|/root|/run|/sbin|/srv|/sys|/tmp|/usr|/usr/bin|/usr/local|/usr/local/bin|/usr/local/lib|/var|/var/lib|/var/log)
      fail_raw "${name} 指向危险路径: ${value}"
      ;;
  esac
}

validate_child_path() {
  local child_name="$1"
  local child
  local parent_name="$3"
  local parent
  child="$(strip_trailing_slash "$2")"
  parent="$(strip_trailing_slash "$4")"

  if [[ "${child}" == "${parent}" || "${child}" != "${parent}/"* ]]; then
    fail_raw "${child_name} 必须位于 ${parent_name} 下: ${child}"
  fi
}

validate_paths() {
  validate_path_value "NEXTARC_INSTALL_DIR" "${NEXTARC_INSTALL_DIR}"
  validate_path_value "NEXTARC_APP_DIR" "${NEXTARC_APP_DIR}"
  validate_path_value "NEXTARC_PYUSTC_DIR" "${NEXTARC_PYUSTC_DIR}"
  validate_path_value "NEXTARC_VENV_DIR" "${NEXTARC_VENV_DIR}"
  validate_path_value "NEXTARC_CONFIG_DIR" "${NEXTARC_CONFIG_DIR}"
  validate_path_value "NEXTARC_STATE_DIR" "${NEXTARC_STATE_DIR}"
  validate_path_value "NEXTARC_LOG_DIR" "${NEXTARC_LOG_DIR}"
  validate_path_value "NEXTARC_ENV_FILE" "${NEXTARC_ENV_FILE}"

  validate_child_path "NEXTARC_APP_DIR" "${NEXTARC_APP_DIR}" "NEXTARC_INSTALL_DIR" "${NEXTARC_INSTALL_DIR}"
  validate_child_path "NEXTARC_PYUSTC_DIR" "${NEXTARC_PYUSTC_DIR}" "NEXTARC_INSTALL_DIR" "${NEXTARC_INSTALL_DIR}"
  validate_child_path "NEXTARC_VENV_DIR" "${NEXTARC_VENV_DIR}" "NEXTARC_INSTALL_DIR" "${NEXTARC_INSTALL_DIR}"
  validate_child_path "NEXTARC_ENV_FILE" "${NEXTARC_ENV_FILE}" "NEXTARC_CONFIG_DIR" "${NEXTARC_CONFIG_DIR}"

  PATHS_VALIDATED="true"
}

write_status() {
  local status="$1"
  local message="$2"
  python3 - "${STATUS_FILE}" "${status}" "${message}" "${NEXTARC_USER}" <<'PY'
from pathlib import Path
import grp
import os
import shlex
import sys
from datetime import datetime

path = Path(sys.argv[1])
status = sys.argv[2]
message = sys.argv[3]
user = sys.argv[4]

path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(
    "NEXTARC_UPGRADE_STATUS=" + shlex.quote(status) + "\n"
    "NEXTARC_UPGRADE_MESSAGE=" + shlex.quote(message) + "\n"
    "NEXTARC_UPGRADE_TIME=" + shlex.quote(datetime.now().isoformat(timespec="seconds")) + "\n",
    encoding="utf-8",
)
try:
    gid = grp.getgrnam(user).gr_gid
    os.chown(path, 0, gid)
    path.chmod(0o640)
except KeyError:
    path.chmod(0o600)
PY
}

stop_nextarc() {
  systemctl stop nextarc || true
}

notify_failure() {
  local message="$1"
  [[ -f "${NEXTARC_ENV_FILE}" && ! -L "${NEXTARC_ENV_FILE}" ]] || return 0

  python3 - "${NEXTARC_ENV_FILE}" "${message}" <<'PY'
from pathlib import Path
import json
import shlex
import sys
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

env_path = Path(sys.argv[1])
message = sys.argv[2]

def read_env(path):
    values = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        try:
            parsed = shlex.split(line, comments=False, posix=True)
        except ValueError:
            parsed = []
        if parsed and "=" in parsed[0]:
            key, value = parsed[0].split("=", 1)
        else:
            key, value = line.split("=", 1)
            value = value.strip().strip("'").strip('"')
        values[key.strip()] = value
    return values

def post_json(url, payload, headers=None):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))

try:
    env = read_env(env_path)
    app_id = env.get("NEXTARC_FEISHU_APP_ID", "")
    app_secret = env.get("NEXTARC_FEISHU_APP_SECRET", "")
    receive_id = env.get("NEXTARC_FEISHU_CHAT_ID") or env.get("NEXTARC_FEISHU_OPEN_ID", "")
    receive_id_type = "chat_id" if env.get("NEXTARC_FEISHU_CHAT_ID") else "open_id"
    if not app_id or not app_secret or not receive_id:
        raise RuntimeError("缺少飞书 app_id/app_secret/chat_id/open_id，跳过失败通知")

    token_result = post_json(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        {"app_id": app_id, "app_secret": app_secret},
    )
    token = token_result.get("tenant_access_token")
    if not token:
        raise RuntimeError(f"获取飞书 tenant_access_token 失败: {token_result.get('msg', 'unknown')}")

    text = (
        "NextArc 自动升级失败，nextarc 服务已停止。\n\n"
        f"失败原因: {message}\n\n"
        "请登录服务器查看: sudo journalctl -u nextarc-upgrade -n 100"
    )
    send_result = post_json(
        f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={receive_id_type}",
        {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        },
        {"Authorization": f"Bearer {token}"},
    )
    if send_result.get("code") not in (0, None):
        raise RuntimeError(f"发送飞书失败: {send_result.get('msg', 'unknown')}")
except (OSError, RuntimeError, HTTPError, URLError, json.JSONDecodeError) as exc:
    print(f"发送升级失败通知失败: {exc}", file=sys.stderr)
PY
}

restore_root_ownership() {
  [[ "${PATHS_VALIDATED}" == "true" ]] || return 0

  chown -R root:root "${NEXTARC_INSTALL_DIR}" || true
  chown -R root:nextarc "${NEXTARC_CONFIG_DIR}" || true
  chown -R nextarc:nextarc "${NEXTARC_STATE_DIR}" "${NEXTARC_LOG_DIR}" || true
  chmod 750 "${NEXTARC_CONFIG_DIR}" "${NEXTARC_STATE_DIR}" "${NEXTARC_LOG_DIR}" || true
  BUILD_OWNERSHIP_GRANTED="false"
}

clear_request_file() {
  [[ "${PATHS_VALIDATED}" == "true" ]] || return 0
  rm -f -- "${REQUEST_FILE}" || true
}

fail() {
  trap - ERR
  local message="$1"
  log "升级失败: ${message}"
  restore_root_ownership
  clear_request_file
  write_status "failed" "${message}" || true
  notify_failure "${message}" || true
  stop_nextarc
  exit 1
}

on_error() {
  local exit_code=$?
  fail "升级脚本异常中断: exit=${exit_code}, line=${BASH_LINENO[0]:-${LINENO}}"
}

trap on_error ERR

require_root() {
  [[ "${EUID}" -eq 0 ]] || fail "升级脚本必须以 root 运行"
}

require_nextarc_user() {
  id "${NEXTARC_USER}" >/dev/null 2>&1 || fail "未找到低权限用户: ${NEXTARC_USER}"
}

run_as_nextarc() {
  runuser -u "${NEXTARC_USER}" -- env HOME="${NEXTARC_STATE_DIR}" "$@"
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

validate_version() {
  local value="$1"
  [[ -z "${value}" || "${value}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
}

require_secure_request_file() {
  [[ -f "${REQUEST_FILE}" ]] || fail "升级请求文件不存在: ${REQUEST_FILE}"
  [[ ! -L "${REQUEST_FILE}" ]] || fail "升级请求文件不能是符号链接: ${REQUEST_FILE}"

  local expected_uid expected_gid file_uid file_gid file_mode file_links
  expected_uid="$(id -u "${NEXTARC_USER}")"
  expected_gid="$(id -g "${NEXTARC_USER}")"
  read -r file_uid file_gid file_mode file_links < <(stat -c '%u %g %a %h' "${REQUEST_FILE}")

  [[ "${file_uid}" == "${expected_uid}" ]] || fail "升级请求文件 owner 不正确: uid=${file_uid}"
  [[ "${file_gid}" == "${expected_gid}" ]] || fail "升级请求文件 group 不正确: gid=${file_gid}"
  [[ "${file_mode}" == "600" ]] || fail "升级请求文件权限必须是 600: mode=${file_mode}"
  [[ "${file_links}" == "1" ]] || fail "升级请求文件硬链接数量异常: links=${file_links}"
}

parse_upgrade_request() {
  local parsed_output
  parsed_output="$(
    python3 - "${REQUEST_FILE}" <<'PY'
from pathlib import Path
import re
import shlex
import sys

request_path = Path(sys.argv[1])
allowed_keys = {
    "NEXTARC_UPGRADE_REMOTE",
    "NEXTARC_UPGRADE_BRANCH",
    "NEXTARC_OLD_VERSION",
}
remote_pattern = re.compile(r"^[A-Za-z0-9._-]+$")
ref_pattern = re.compile(r"^[A-Za-z0-9._/-]+$")
version_pattern = re.compile(r"^\d+\.\d+\.\d+$")

values = {}
for lineno, raw_line in enumerate(request_path.read_text(encoding="utf-8").splitlines(), 1):
    line = raw_line.strip()
    if not line or line.startswith("#"):
        continue
    if "=" not in line:
        raise SystemExit(f"第 {lineno} 行不是 KEY=VALUE 格式")
    key, raw_value = line.split("=", 1)
    key = key.strip()
    raw_value = raw_value.strip()
    if key not in allowed_keys:
        raise SystemExit(f"第 {lineno} 行包含不允许的字段: {key}")
    try:
        parts = shlex.split(raw_value, comments=False, posix=True) if raw_value else []
    except ValueError as exc:
        raise SystemExit(f"第 {lineno} 行无法解析: {exc}") from exc
    if len(parts) > 1:
        raise SystemExit(f"第 {lineno} 行只能包含一个值")
    values[key] = parts[0] if parts else ""

remote = values.get("NEXTARC_UPGRADE_REMOTE", "")
branch = values.get("NEXTARC_UPGRADE_BRANCH", "")
old_version = values.get("NEXTARC_OLD_VERSION", "")

if not remote_pattern.fullmatch(remote):
    raise SystemExit("远程仓库名称缺失或格式不安全")
if (
    not branch
    or branch.startswith("-")
    or ".." in branch
    or branch.endswith(".lock")
    or not ref_pattern.fullmatch(branch)
):
    raise SystemExit("分支名称缺失或格式不安全")
if old_version and not version_pattern.fullmatch(old_version):
    raise SystemExit("旧版本号格式不安全")

print(f"{remote}\t{branch}\t{old_version}")
PY
  )" || fail "升级请求文件解析失败"

  IFS=$'\t' read -r NEXTARC_UPGRADE_REMOTE NEXTARC_UPGRADE_BRANCH NEXTARC_OLD_VERSION <<<"${parsed_output}"

  validate_remote "${NEXTARC_UPGRADE_REMOTE}" || fail "远程仓库名称不安全: ${NEXTARC_UPGRADE_REMOTE}"
  validate_ref "${NEXTARC_UPGRADE_BRANCH}" || fail "分支名称不安全: ${NEXTARC_UPGRADE_BRANCH}"
  validate_version "${NEXTARC_OLD_VERSION}" || fail "旧版本号格式不安全: ${NEXTARC_OLD_VERSION}"
}

require_installed_layout() {
  [[ -d "${NEXTARC_APP_DIR}/.git" ]] || fail "NextArc 目录不是 git 仓库: ${NEXTARC_APP_DIR}"
  [[ -d "${NEXTARC_PYUSTC_DIR}/.git" ]] || fail "pyustc 目录不是 git 仓库: ${NEXTARC_PYUSTC_DIR}"
  [[ -x "${NEXTARC_VENV_DIR}/bin/pip" ]] || fail "虚拟环境不可用: ${NEXTARC_VENV_DIR}"
  [[ -x "${NEXTARC_VENV_DIR}/bin/python" ]] || fail "虚拟环境 Python 不可用: ${NEXTARC_VENV_DIR}"
}

ensure_clean_git_tree() {
  local repo_dir="$1"
  local label="$2"
  local reject_untracked="${3:-true}"
  local status

  git -C "${repo_dir}" diff --quiet || fail "${label} 存在未提交的工作区修改"
  git -C "${repo_dir}" diff --cached --quiet || fail "${label} 存在未提交的暂存区修改"
  if [[ "${reject_untracked}" == "true" ]]; then
    status="$(git -C "${repo_dir}" status --porcelain)" || fail "无法读取 ${label} git 状态"
    [[ -z "${status}" ]] || fail "${label} 存在未提交或未跟踪文件，拒绝自动升级"
  else
    status="$(git -C "${repo_dir}" status --porcelain --untracked-files=no)" || fail "无法读取 ${label} git 状态"
    [[ -z "${status}" ]] || fail "${label} 存在未提交的跟踪文件修改，拒绝自动升级"
  fi
}

ensure_pyustc_upstream() {
  git -C "${NEXTARC_PYUSTC_DIR}" rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null \
    || fail "pyustc 当前分支没有配置上游，无法安全执行 pull --ff-only"
}

grant_build_ownership() {
  chown -R "${NEXTARC_USER}:${NEXTARC_USER}" "${NEXTARC_APP_DIR}" "${NEXTARC_PYUSTC_DIR}" "${NEXTARC_VENV_DIR}"
  BUILD_OWNERSHIP_GRANTED="true"
}

run_low_privilege_upgrade() {
  local remote="$1"
  local branch="$2"

  log "确认远端分支存在: ${remote}/${branch}"
  run_as_nextarc git -C "${NEXTARC_APP_DIR}" remote get-url "${remote}" >/dev/null \
    || fail "NextArc 远程仓库不存在: ${remote}"
  run_as_nextarc git -C "${NEXTARC_APP_DIR}" ls-remote --exit-code --heads "${remote}" "${branch}" >/dev/null \
    || fail "NextArc 远端分支不存在或不可访问: ${remote}/${branch}"

  log "更新 NextArc: ${remote}/${branch}"
  run_as_nextarc git -C "${NEXTARC_APP_DIR}" fetch "${remote}" "+refs/heads/${branch}:refs/remotes/${remote}/${branch}" \
    || fail "NextArc fetch 失败"
  if run_as_nextarc git -C "${NEXTARC_APP_DIR}" show-ref --verify --quiet "refs/heads/${branch}"; then
    run_as_nextarc git -C "${NEXTARC_APP_DIR}" switch "${branch}" || fail "切换 NextArc 分支失败"
  else
    run_as_nextarc git -C "${NEXTARC_APP_DIR}" switch --track -c "${branch}" "${remote}/${branch}" \
      || fail "创建 NextArc 跟踪分支失败"
  fi
  run_as_nextarc git -C "${NEXTARC_APP_DIR}" pull --ff-only "${remote}" "${branch}" || fail "NextArc pull 失败"

  log "更新 pyustc"
  run_as_nextarc git -C "${NEXTARC_PYUSTC_DIR}" pull --ff-only || fail "pyustc pull 失败"

  log "在虚拟环境中安装 NextArc 依赖"
  run_as_nextarc env PIP_DISABLE_PIP_VERSION_CHECK=1 "${NEXTARC_VENV_DIR}/bin/pip" install -r "${NEXTARC_APP_DIR}/requirements.txt" \
    || fail "安装 NextArc 依赖失败"

  log "在虚拟环境中安装 pyustc"
  run_as_nextarc env PIP_DISABLE_PIP_VERSION_CHECK=1 "${NEXTARC_VENV_DIR}/bin/pip" install -e "${NEXTARC_PYUSTC_DIR}" \
    || fail "安装 pyustc 失败"

  log "执行升级后基础校验"
  run_as_nextarc "${NEXTARC_VENV_DIR}/bin/python" -m compileall -q "${NEXTARC_APP_DIR}/src" "${NEXTARC_PYUSTC_DIR}" \
    || fail "Python 编译检查失败"
  run_as_nextarc "${NEXTARC_VENV_DIR}/bin/python" -m pip check || fail "pip 依赖一致性检查失败"
}

write_update_marker() {
  printf '%s\n' "${NEXTARC_OLD_VERSION}" >"${MARKER_FILE}"
  chown nextarc:nextarc "${MARKER_FILE}"
  chmod 600 "${MARKER_FILE}"
}

main() {
  validate_paths
  require_root
  require_nextarc_user

  exec 9>"${LOCK_FILE}"
  flock -n 9 || fail "已有升级任务正在运行"

  require_secure_request_file
  parse_upgrade_request
  require_installed_layout
  ensure_clean_git_tree "${NEXTARC_APP_DIR}" "NextArc" "true"
  ensure_clean_git_tree "${NEXTARC_PYUSTC_DIR}" "pyustc" "false"
  ensure_pyustc_upstream

  write_status "running" "正在升级到 ${NEXTARC_UPGRADE_REMOTE}/${NEXTARC_UPGRADE_BRANCH}"
  log "停止 nextarc 服务"
  systemctl stop nextarc || fail "停止 nextarc 服务失败"
  if systemctl is-active --quiet nextarc; then
    fail "nextarc 服务仍处于运行状态，拒绝升级"
  fi

  log "将拉取和构建权限临时交给低权限用户: ${NEXTARC_USER}"
  grant_build_ownership
  run_low_privilege_upgrade "${NEXTARC_UPGRADE_REMOTE}" "${NEXTARC_UPGRADE_BRANCH}"

  log "收回安装目录权限"
  restore_root_ownership

  write_update_marker
  clear_request_file

  log "启动 nextarc 服务"
  systemctl start nextarc || fail "nextarc 服务启动失败"
  sleep 2
  systemctl is-active --quiet nextarc || fail "nextarc 服务启动后未保持 active"

  write_status "succeeded" "升级完成"
  log "升级完成"
}

main "$@"
