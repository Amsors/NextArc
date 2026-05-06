#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NEXTARC_GITHUB_REPO_URL="https://github.com/Amsors/NextArc"
PYUSTC_GITHUB_REPO_URL="https://github.com/Amsors/pyustc"
NEXTARC_LUG_GITLAB_REPO_URL="https://git.lug.ustc.edu.cn/amsors/nextarc_mirror"
PYUSTC_LUG_GITLAB_REPO_URL="https://git.lug.ustc.edu.cn/amsors/pyustc_mirror"

NEXTARC_REPO_ORIGIN="${NEXTARC_REPO_ORIGIN:-lug_gitlab}"
NEXTARC_REPO_URL="${NEXTARC_REPO_URL:-}"
NEXTARC_REPO_BRANCH="${NEXTARC_REPO_BRANCH:-feat/one_click_deploy}"
PYUSTC_REPO_URL="${PYUSTC_REPO_URL:-}"
PYUSTC_REPO_BRANCH="${PYUSTC_REPO_BRANCH:-adapt/NextArc}"

NEXTARC_INSTALL_DIR="${NEXTARC_INSTALL_DIR:-/opt/nextarc}"
NEXTARC_APP_DIR="${NEXTARC_APP_DIR:-/opt/nextarc/app}"
NEXTARC_PYUSTC_DIR="${NEXTARC_PYUSTC_DIR:-/opt/nextarc/pyustc}"
NEXTARC_VENV_DIR="${NEXTARC_VENV_DIR:-/opt/nextarc/venv}"
NEXTARC_CONFIG_DIR="${NEXTARC_CONFIG_DIR:-/etc/nextarc}"
NEXTARC_STATE_DIR="${NEXTARC_STATE_DIR:-/var/lib/nextarc}"
NEXTARC_LOG_DIR="${NEXTARC_LOG_DIR:-/var/log/nextarc}"
NEXTARC_ENV_FILE="${NEXTARC_ENV_FILE:-/etc/nextarc/nextarc.env}"
NEXTARC_SERVICE_FILE="/etc/systemd/system/nextarc.service"
NEXTARC_UPGRADE_SERVICE_FILE="/etc/systemd/system/nextarc-upgrade.service"
NEXTARC_UPGRADE_PATH_FILE="/etc/systemd/system/nextarc-upgrade.path"
NEXTARC_LIB_DIR="${NEXTARC_LIB_DIR:-/usr/local/lib/nextarc}"
NEXTARC_UPGRADE_SCRIPT="${NEXTARC_LIB_DIR}/upgrade-nextarc.sh"
NEXTARC_SUDOERS_FILE="/etc/sudoers.d/nextarc-upgrade"

log_step() {
  echo
  echo "==> $*"
}

log_info() {
  echo "    $*"
}

usage() {
  cat <<'EOF'
Usage:
  install-nextarc.sh [--origin github|lug_gitlab] [--skip-feishu-register]
  install-nextarc.sh --migrate /path/to/old_nextarc
  install-nextarc.sh --uninstall
  install-nextarc.sh --purge

Default origin:
  lug_gitlab

Environment overrides:
  NEXTARC_REPO_ORIGIN
  NEXTARC_REPO_URL
  NEXTARC_REPO_BRANCH
  PYUSTC_REPO_URL
  PYUSTC_REPO_BRANCH
EOF
}

parse_args() {
  ACTION="install"
  MIGRATE_SOURCE_DIR=""
  SKIP_FEISHU_REGISTER="false"

  while [[ "$#" -gt 0 ]]; do
    case "$1" in
      -h|--help)
        ACTION="help"
        shift
        ;;
      --uninstall)
        ACTION="uninstall"
        shift
        ;;
      --purge)
        ACTION="purge"
        shift
        ;;
      --skip-feishu-register|--skip-feishu)
        SKIP_FEISHU_REGISTER="true"
        shift
        ;;
      --migrate)
        if [[ "$#" -lt 2 ]]; then
          echo "--migrate 需要指定旧 NextArc 项目根目录" >&2
          usage >&2
          exit 1
        fi
        ACTION="migrate"
        MIGRATE_SOURCE_DIR="$2"
        shift 2
        ;;
      --migrate=*)
        ACTION="migrate"
        MIGRATE_SOURCE_DIR="${1#--migrate=}"
        shift
        ;;
      --origin)
        if [[ "$#" -lt 2 ]]; then
          echo "--origin 需要指定 github 或 lug_gitlab" >&2
          usage >&2
          exit 1
        fi
        NEXTARC_REPO_ORIGIN="$2"
        shift 2
        ;;
      --origin=*)
        NEXTARC_REPO_ORIGIN="${1#--origin=}"
        shift
        ;;
      *)
        usage >&2
        exit 1
        ;;
    esac
  done
}

configure_repo_urls() {
  case "${NEXTARC_REPO_ORIGIN}" in
    github)
      NEXTARC_REPO_URL="${NEXTARC_REPO_URL:-${NEXTARC_GITHUB_REPO_URL}}"
      PYUSTC_REPO_URL="${PYUSTC_REPO_URL:-${PYUSTC_GITHUB_REPO_URL}}"
      ;;
    lug_gitlab)
      NEXTARC_REPO_URL="${NEXTARC_REPO_URL:-${NEXTARC_LUG_GITLAB_REPO_URL}}"
      PYUSTC_REPO_URL="${PYUSTC_REPO_URL:-${PYUSTC_LUG_GITLAB_REPO_URL}}"
      ;;
    *)
      echo "不支持的仓库来源: ${NEXTARC_REPO_ORIGIN}" >&2
      echo "可用来源: github, lug_gitlab" >&2
      exit 1
      ;;
  esac
}

strip_trailing_slash() {
  local path="$1"
  while [[ "${path}" != "/" && "${path}" == */ ]]; do
    path="${path%/}"
  done
  printf '%s\n' "${path}"
}

validate_path_value() {
  local name="$1"
  local value
  value="$(strip_trailing_slash "$2")"

  if [[ -z "${value}" ]]; then
    echo "${name} 不能为空" >&2
    exit 1
  fi
  if [[ "${value}" != /* ]]; then
    echo "${name} 必须是绝对路径: ${value}" >&2
    exit 1
  fi
  case "/${value#/}/" in
    */../*|*/./*)
      echo "${name} 不能包含 . 或 .. 路径组件: ${value}" >&2
      exit 1
      ;;
  esac
  if [[ -L "${value}" ]]; then
    echo "${name} 不能是符号链接: ${value}" >&2
    exit 1
  fi

  case "${value}" in
    *$'\n'*|*$'\r'*|*[[:space:]]*)
      echo "${name} 不能包含空白字符: ${value}" >&2
      exit 1
      ;;
  esac

  case "${value}" in
    /|/bin|/boot|/dev|/etc|/home|/lib|/lib64|/opt|/proc|/root|/run|/sbin|/srv|/sys|/tmp|/usr|/usr/bin|/usr/local|/usr/local/bin|/usr/local/lib|/var|/var/lib|/var/log)
      echo "${name} 指向危险路径: ${value}" >&2
      exit 1
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
    echo "${child_name} 必须位于 ${parent_name} 下: ${child}" >&2
    exit 1
  fi
}

validate_git_ref() {
  local name="$1"
  local value="$2"
  if (
    [[ -z "${value}" ]] ||
    [[ "${value}" == -* ]] ||
    [[ "${value}" == *..* ]] ||
    [[ "${value}" == *.lock ]] ||
    [[ ! "${value}" =~ ^[A-Za-z0-9._/-]+$ ]]
  ); then
    echo "${name} 不是安全的 git ref: ${value}" >&2
    exit 1
  fi
}

validate_install_paths() {
  validate_path_value "NEXTARC_INSTALL_DIR" "${NEXTARC_INSTALL_DIR}"
  validate_path_value "NEXTARC_APP_DIR" "${NEXTARC_APP_DIR}"
  validate_path_value "NEXTARC_PYUSTC_DIR" "${NEXTARC_PYUSTC_DIR}"
  validate_path_value "NEXTARC_VENV_DIR" "${NEXTARC_VENV_DIR}"
  validate_path_value "NEXTARC_CONFIG_DIR" "${NEXTARC_CONFIG_DIR}"
  validate_path_value "NEXTARC_STATE_DIR" "${NEXTARC_STATE_DIR}"
  validate_path_value "NEXTARC_LOG_DIR" "${NEXTARC_LOG_DIR}"
  validate_path_value "NEXTARC_ENV_FILE" "${NEXTARC_ENV_FILE}"
  validate_path_value "NEXTARC_LIB_DIR" "${NEXTARC_LIB_DIR}"
  validate_path_value "NEXTARC_UPGRADE_SCRIPT" "${NEXTARC_UPGRADE_SCRIPT}"

  validate_child_path "NEXTARC_APP_DIR" "${NEXTARC_APP_DIR}" "NEXTARC_INSTALL_DIR" "${NEXTARC_INSTALL_DIR}"
  validate_child_path "NEXTARC_PYUSTC_DIR" "${NEXTARC_PYUSTC_DIR}" "NEXTARC_INSTALL_DIR" "${NEXTARC_INSTALL_DIR}"
  validate_child_path "NEXTARC_VENV_DIR" "${NEXTARC_VENV_DIR}" "NEXTARC_INSTALL_DIR" "${NEXTARC_INSTALL_DIR}"
  validate_child_path "NEXTARC_ENV_FILE" "${NEXTARC_ENV_FILE}" "NEXTARC_CONFIG_DIR" "${NEXTARC_CONFIG_DIR}"
  validate_child_path "NEXTARC_UPGRADE_SCRIPT" "${NEXTARC_UPGRADE_SCRIPT}" "NEXTARC_LIB_DIR" "${NEXTARC_LIB_DIR}"
}

validate_repo_refs() {
  validate_git_ref "NEXTARC_REPO_BRANCH" "${NEXTARC_REPO_BRANCH}"
  validate_git_ref "PYUSTC_REPO_BRANCH" "${PYUSTC_REPO_BRANCH}"
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "请使用 root 权限运行，例如：sudo bash install-nextarc.sh" >&2
    exit 1
  fi
}

uninstall_service() {
  log_step "卸载 NextArc systemd 服务"
  log_info "停止并禁用服务: nextarc"
  systemctl disable --now nextarc >/dev/null 2>&1 || true
  log_info "停止升级服务: nextarc-upgrade"
  systemctl disable --now nextarc-upgrade.path >/dev/null 2>&1 || true
  systemctl stop nextarc-upgrade >/dev/null 2>&1 || true
  log_info "删除服务文件: ${NEXTARC_SERVICE_FILE}"
  rm -f "${NEXTARC_SERVICE_FILE}"
  log_info "删除升级服务文件: ${NEXTARC_UPGRADE_SERVICE_FILE}"
  rm -f "${NEXTARC_UPGRADE_SERVICE_FILE}"
  log_info "删除升级监听文件: ${NEXTARC_UPGRADE_PATH_FILE}"
  rm -f "${NEXTARC_UPGRADE_PATH_FILE}"
  log_info "删除升级脚本: ${NEXTARC_UPGRADE_SCRIPT}"
  rm -f "${NEXTARC_UPGRADE_SCRIPT}"
  log_info "删除 sudoers 白名单: ${NEXTARC_SUDOERS_FILE}"
  rm -f "${NEXTARC_SUDOERS_FILE}"
  log_info "重新加载 systemd 配置"
  systemctl daemon-reload
  log_info "清理 systemd failed 状态"
  systemctl reset-failed nextarc >/dev/null 2>&1 || true
  systemctl reset-failed nextarc-upgrade >/dev/null 2>&1 || true
  systemctl reset-failed nextarc-upgrade.path >/dev/null 2>&1 || true
  echo "NextArc systemd 服务已卸载。配置、数据、日志和代码均已保留。"
}

purge_all() {
  uninstall_service
  echo
  echo "危险操作：这将删除 NextArc 代码、配置、飞书凭据、USTC 凭据、数据和日志。"
  echo "将删除的路径："
  echo "  - ${NEXTARC_INSTALL_DIR}"
  echo "  - ${NEXTARC_CONFIG_DIR}"
  echo "  - ${NEXTARC_STATE_DIR}"
  echo "  - ${NEXTARC_LOG_DIR}"
  echo "  - ${NEXTARC_LIB_DIR}"
  echo "将删除的系统用户：nextarc"
  read -r -p "如确认删除，请输入 DELETE NEXTARC: " confirmation
  if [[ "${confirmation}" != "DELETE NEXTARC" ]]; then
    echo "已取消彻底卸载。"
    exit 1
  fi
  log_step "删除 NextArc 文件和目录"
  log_info "删除代码和虚拟环境: ${NEXTARC_INSTALL_DIR}"
  log_info "删除配置和密钥: ${NEXTARC_CONFIG_DIR}"
  log_info "删除运行数据: ${NEXTARC_STATE_DIR}"
  log_info "删除日志目录: ${NEXTARC_LOG_DIR}"
  log_info "删除维护脚本目录: ${NEXTARC_LIB_DIR}"
  rm -rf "${NEXTARC_INSTALL_DIR}" "${NEXTARC_CONFIG_DIR}" "${NEXTARC_STATE_DIR}" "${NEXTARC_LOG_DIR}" "${NEXTARC_LIB_DIR}"
  log_step "删除系统用户"
  log_info "删除用户: nextarc"
  userdel nextarc >/dev/null 2>&1 || true
  echo "NextArc 已彻底卸载。"
}

install_packages() {
  log_step "安装系统依赖"
  log_info "更新 apt 软件包索引"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  log_info "安装软件包: git curl ca-certificates sudo python3 python3-venv python3-pip sqlite3"
  apt-get install -y git curl ca-certificates sudo python3 python3-venv python3-pip sqlite3
}

ensure_user_and_dirs() {
  log_step "创建运行用户和目录"
  if ! id nextarc >/dev/null 2>&1; then
    log_info "创建系统用户: nextarc"
    useradd --system --home "${NEXTARC_STATE_DIR}" --shell /usr/sbin/nologin nextarc
  else
    log_info "系统用户已存在: nextarc"
  fi

  log_info "创建安装目录: ${NEXTARC_INSTALL_DIR}"
  log_info "创建配置目录: ${NEXTARC_CONFIG_DIR}"
  log_info "创建状态目录: ${NEXTARC_STATE_DIR}"
  log_info "创建日志目录: ${NEXTARC_LOG_DIR}"
  mkdir -p "${NEXTARC_INSTALL_DIR}" "${NEXTARC_CONFIG_DIR}" "${NEXTARC_STATE_DIR}" "${NEXTARC_LOG_DIR}"
  log_info "设置状态和日志目录所有者为 nextarc:nextarc"
  chown -R nextarc:nextarc "${NEXTARC_STATE_DIR}" "${NEXTARC_LOG_DIR}"
  log_info "设置配置、状态和日志目录权限为 750"
  chmod 750 "${NEXTARC_CONFIG_DIR}" "${NEXTARC_STATE_DIR}" "${NEXTARC_LOG_DIR}"
}

checkout_code() {
  log_step "获取 NextArc 代码"
  log_info "来源: ${NEXTARC_REPO_ORIGIN}"
  log_info "仓库: ${NEXTARC_REPO_URL}"
  log_info "分支: ${NEXTARC_REPO_BRANCH}"
  log_info "目标目录: ${NEXTARC_APP_DIR}"
  if [[ -d "${NEXTARC_APP_DIR}/.git" ]]; then
    log_info "检测到已有 git 仓库，拉取最新代码"
    git -C "${NEXTARC_APP_DIR}" remote set-url origin "${NEXTARC_REPO_URL}"
    git -C "${NEXTARC_APP_DIR}" fetch origin "${NEXTARC_REPO_BRANCH}"
    git -C "${NEXTARC_APP_DIR}" checkout "${NEXTARC_REPO_BRANCH}"
    git -C "${NEXTARC_APP_DIR}" pull --ff-only origin "${NEXTARC_REPO_BRANCH}"
  else
    log_info "未检测到已有仓库，清理目标目录并重新克隆"
    rm -rf "${NEXTARC_APP_DIR}"
    git clone --branch "${NEXTARC_REPO_BRANCH}" --single-branch "${NEXTARC_REPO_URL}" "${NEXTARC_APP_DIR}"
  fi
}

checkout_pyustc() {
  log_step "获取 pyustc 代码"
  log_info "来源: ${NEXTARC_REPO_ORIGIN}"
  log_info "仓库: ${PYUSTC_REPO_URL}"
  log_info "分支: ${PYUSTC_REPO_BRANCH}"
  log_info "目标目录: ${NEXTARC_PYUSTC_DIR}"
  if [[ -d "${NEXTARC_PYUSTC_DIR}/.git" ]]; then
    log_info "检测到已有 pyustc 仓库，拉取最新代码"
    git -C "${NEXTARC_PYUSTC_DIR}" remote set-url origin "${PYUSTC_REPO_URL}"
    git -C "${NEXTARC_PYUSTC_DIR}" fetch origin "${PYUSTC_REPO_BRANCH}"
    git -C "${NEXTARC_PYUSTC_DIR}" checkout "${PYUSTC_REPO_BRANCH}"
    git -C "${NEXTARC_PYUSTC_DIR}" pull --ff-only origin "${PYUSTC_REPO_BRANCH}"
  else
    log_info "未检测到已有 pyustc 仓库，清理目标目录并重新克隆"
    rm -rf "${NEXTARC_PYUSTC_DIR}"
    git clone --branch "${PYUSTC_REPO_BRANCH}" --single-branch "${PYUSTC_REPO_URL}" "${NEXTARC_PYUSTC_DIR}"
  fi
}

install_python_deps() {
  log_step "创建 Python 虚拟环境并安装依赖"
  log_info "虚拟环境目录: ${NEXTARC_VENV_DIR}"
  python3 -m venv "${NEXTARC_VENV_DIR}"
  log_info "升级 pip 和 wheel"
  "${NEXTARC_VENV_DIR}/bin/python" -m pip install --upgrade pip wheel
  log_info "安装项目依赖: ${NEXTARC_APP_DIR}/requirements.txt"
  "${NEXTARC_VENV_DIR}/bin/pip" install -r "${NEXTARC_APP_DIR}/requirements.txt"
  log_info "以 editable 模式安装 pyustc: ${NEXTARC_PYUSTC_DIR}"
  "${NEXTARC_VENV_DIR}/bin/pip" install -e "${NEXTARC_PYUSTC_DIR}"

  log_info "写入 nextarc 命令包装脚本: ${NEXTARC_VENV_DIR}/bin/nextarc"
  cat >"${NEXTARC_VENV_DIR}/bin/nextarc" <<EOF
#!/usr/bin/env bash
cd "${NEXTARC_APP_DIR}"
exec "${NEXTARC_VENV_DIR}/bin/python" -m src.cli "\$@"
EOF
  log_info "设置 nextarc 命令权限为 755"
  chmod 755 "${NEXTARC_VENV_DIR}/bin/nextarc"
}

install_upgrade_service() {
  log_step "安装自升级服务"
  log_info "创建维护脚本目录: ${NEXTARC_LIB_DIR}"
  mkdir -p "${NEXTARC_LIB_DIR}"
  log_info "写入升级脚本: ${NEXTARC_UPGRADE_SCRIPT}"
  install -m 0755 "${SCRIPT_DIR}/upgrade-nextarc.sh" "${NEXTARC_UPGRADE_SCRIPT}"

  log_info "写入升级服务文件: ${NEXTARC_UPGRADE_SERVICE_FILE}"
  cat >"${NEXTARC_UPGRADE_SERVICE_FILE}" <<EOF
[Unit]
Description=NextArc Self Upgrade
Documentation=https://github.com/Amsors/NextArc
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=root
Group=root
UMask=0077
Environment=NEXTARC_APP_DIR=${NEXTARC_APP_DIR}
Environment=NEXTARC_INSTALL_DIR=${NEXTARC_INSTALL_DIR}
Environment=NEXTARC_PYUSTC_DIR=${NEXTARC_PYUSTC_DIR}
Environment=NEXTARC_VENV_DIR=${NEXTARC_VENV_DIR}
Environment=NEXTARC_CONFIG_DIR=${NEXTARC_CONFIG_DIR}
Environment=NEXTARC_STATE_DIR=${NEXTARC_STATE_DIR}
Environment=NEXTARC_LOG_DIR=${NEXTARC_LOG_DIR}
Environment=NEXTARC_ENV_FILE=${NEXTARC_ENV_FILE}
ExecStart=${NEXTARC_UPGRADE_SCRIPT}
TimeoutStartSec=900
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=full
ReadWritePaths=${NEXTARC_INSTALL_DIR} ${NEXTARC_CONFIG_DIR} ${NEXTARC_STATE_DIR} ${NEXTARC_LOG_DIR}
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
SystemCallArchitectures=native
EOF
  chmod 0644 "${NEXTARC_UPGRADE_SERVICE_FILE}"

  log_info "写入升级请求监听文件: ${NEXTARC_UPGRADE_PATH_FILE}"
  cat >"${NEXTARC_UPGRADE_PATH_FILE}" <<EOF
[Unit]
Description=Watch NextArc Self Upgrade Requests
Documentation=https://github.com/Amsors/NextArc

[Path]
PathExists=${NEXTARC_STATE_DIR}/upgrade-request.env
PathChanged=${NEXTARC_STATE_DIR}/upgrade-request.env
Unit=nextarc-upgrade.service

[Install]
WantedBy=multi-user.target
EOF
  chmod 0644 "${NEXTARC_UPGRADE_PATH_FILE}"

  log_info "移除旧版 sudoers 白名单: ${NEXTARC_SUDOERS_FILE}"
  rm -f "${NEXTARC_SUDOERS_FILE}"
}

run_bootstrap_if_needed() {
  log_step "初始化 NextArc 配置"
  if [[ -f "${NEXTARC_ENV_FILE}" && -f "${NEXTARC_CONFIG_DIR}/config.yaml" ]]; then
    log_info "检测到已有环境文件: ${NEXTARC_ENV_FILE}"
    log_info "检测到已有配置文件: ${NEXTARC_CONFIG_DIR}/config.yaml"
    log_info "跳过初始化向导"
    return
  fi

  log_info "将启动交互式初始化向导"
  log_info "配置文件: ${NEXTARC_CONFIG_DIR}/config.yaml"
  log_info "偏好配置: ${NEXTARC_CONFIG_DIR}/preferences.yaml"
  log_info "敏感环境变量: ${NEXTARC_ENV_FILE}"
  log_info "运行态状态: ${NEXTARC_STATE_DIR}/state.yaml"
  local bootstrap_args=()
  if [[ "${SKIP_FEISHU_REGISTER}" == "true" ]]; then
    log_info "将跳过飞书应用创建，之后可通过 --migrate 或 nextarc feishu-register 补充凭据"
    bootstrap_args+=(--skip-feishu-register)
  fi

  NEXTARC_CONFIG_DIR="${NEXTARC_CONFIG_DIR}" \
  NEXTARC_STATE_DIR="${NEXTARC_STATE_DIR}" \
  NEXTARC_LOG_DIR="${NEXTARC_LOG_DIR}" \
  NEXTARC_ENV_FILE="${NEXTARC_ENV_FILE}" \
  NEXTARC_REPO_BRANCH="${NEXTARC_REPO_BRANCH}" \
  NEXTARC_CONFIG="${NEXTARC_CONFIG_DIR}/config.yaml" \
  NEXTARC_PREFERENCES="${NEXTARC_CONFIG_DIR}/preferences.yaml" \
  NEXTARC_STATE="${NEXTARC_STATE_DIR}/state.yaml" \
    "${NEXTARC_VENV_DIR}/bin/nextarc" bootstrap "${bootstrap_args[@]}"
}

fix_permissions() {
  log_step "修正文件权限"
  log_info "设置安装目录所有者: root:root ${NEXTARC_INSTALL_DIR}"
  chown -R root:root "${NEXTARC_INSTALL_DIR}"
  log_info "设置配置目录所有者: root:nextarc ${NEXTARC_CONFIG_DIR}"
  chown -R root:nextarc "${NEXTARC_CONFIG_DIR}"
  log_info "设置状态和日志目录所有者: nextarc:nextarc"
  chown -R nextarc:nextarc "${NEXTARC_STATE_DIR}" "${NEXTARC_LOG_DIR}"
  log_info "设置配置、状态和日志目录权限为 750"
  chmod 750 "${NEXTARC_CONFIG_DIR}" "${NEXTARC_STATE_DIR}" "${NEXTARC_LOG_DIR}"
  if [[ -f "${NEXTARC_ENV_FILE}" ]]; then
    log_info "设置环境变量文件权限为 640: ${NEXTARC_ENV_FILE}"
    chmod 640 "${NEXTARC_ENV_FILE}"
  fi
}

require_installed_service() {
  log_step "检查 daemon 化安装状态"
  [[ -f "${NEXTARC_SERVICE_FILE}" ]] || {
    echo "未找到 systemd 服务文件: ${NEXTARC_SERVICE_FILE}" >&2
    echo "请先以服务化形式安装 NextArc，再执行迁移。" >&2
    exit 1
  }
  [[ -d "${NEXTARC_APP_DIR}" ]] || {
    echo "未找到应用目录: ${NEXTARC_APP_DIR}" >&2
    echo "请先以服务化形式安装 NextArc，再执行迁移。" >&2
    exit 1
  }
  [[ -d "${NEXTARC_CONFIG_DIR}" ]] || {
    echo "未找到配置目录: ${NEXTARC_CONFIG_DIR}" >&2
    echo "请先以服务化形式安装 NextArc，再执行迁移。" >&2
    exit 1
  }
  [[ -d "${NEXTARC_STATE_DIR}" ]] || {
    echo "未找到状态目录: ${NEXTARC_STATE_DIR}" >&2
    echo "请先以服务化形式安装 NextArc，再执行迁移。" >&2
    exit 1
  }
  [[ -x "${NEXTARC_VENV_DIR}/bin/python" ]] || {
    echo "未找到可用虚拟环境: ${NEXTARC_VENV_DIR}" >&2
    echo "请先以服务化形式安装 NextArc，再执行迁移。" >&2
    exit 1
  }
  id nextarc >/dev/null 2>&1 || {
    echo "未找到运行用户: nextarc" >&2
    echo "请先以服务化形式安装 NextArc，再执行迁移。" >&2
    exit 1
  }
  log_info "daemon 化安装状态检查通过"
}

validate_migration_source() {
  if [[ -z "${MIGRATE_SOURCE_DIR}" ]]; then
    echo "未指定旧 NextArc 项目根目录" >&2
    usage >&2
    exit 1
  fi

  MIGRATE_SOURCE_DIR="$(cd "${MIGRATE_SOURCE_DIR}" 2>/dev/null && pwd -P)" || {
    echo "旧 NextArc 项目根目录不存在或不可访问: ${MIGRATE_SOURCE_DIR}" >&2
    exit 1
  }
  local daemon_app_dir
  daemon_app_dir="$(cd "${NEXTARC_APP_DIR}" 2>/dev/null && pwd -P)" || daemon_app_dir=""
  if [[ -n "${daemon_app_dir}" && "${MIGRATE_SOURCE_DIR}" == "${daemon_app_dir}" ]]; then
    echo "旧 NextArc 项目根目录不能是当前 daemon 应用目录: ${NEXTARC_APP_DIR}" >&2
    exit 1
  fi

  log_step "检查旧 NextArc 数据"
  log_info "旧项目目录: ${MIGRATE_SOURCE_DIR}"
  [[ -f "${MIGRATE_SOURCE_DIR}/config/config.yaml" ]] || {
    echo "旧配置文件不存在: ${MIGRATE_SOURCE_DIR}/config/config.yaml" >&2
    exit 1
  }
  [[ -f "${MIGRATE_SOURCE_DIR}/config/preferences.yaml" ]] || {
    echo "旧偏好配置文件不存在: ${MIGRATE_SOURCE_DIR}/config/preferences.yaml" >&2
    exit 1
  }
  [[ -d "${MIGRATE_SOURCE_DIR}/data" ]] || {
    echo "旧数据目录不存在: ${MIGRATE_SOURCE_DIR}/data" >&2
    exit 1
  }

  shopt -s nullglob
  MIGRATE_DB_FILES=("${MIGRATE_SOURCE_DIR}"/data/*.db)
  shopt -u nullglob
  if [[ "${#MIGRATE_DB_FILES[@]}" -eq 0 ]]; then
    echo "旧数据目录中未找到 .db 文件: ${MIGRATE_SOURCE_DIR}/data" >&2
    exit 1
  fi

  log_info "检测到配置文件: config/config.yaml"
  log_info "检测到偏好配置: config/preferences.yaml"
  log_info "检测到数据库文件数量: ${#MIGRATE_DB_FILES[@]}"
}

rewrite_migrated_config_paths() {
  log_info "修正 daemon 运行所需数据库路径: ${NEXTARC_CONFIG_DIR}/config.yaml"
  "${NEXTARC_VENV_DIR}/bin/python" - "${NEXTARC_CONFIG_DIR}/config.yaml" "${NEXTARC_STATE_DIR}/data" <<'PY'
from pathlib import Path
import sys

import yaml

config_path = Path(sys.argv[1])
data_dir = Path(sys.argv[2])

with config_path.open("r", encoding="utf-8") as f:
    config = yaml.safe_load(f) or {}

database = config.setdefault("database", {})
database["data_dir"] = str(data_dir)
database["preference_db_path"] = str(data_dir / "user_preference.db")

with config_path.open("w", encoding="utf-8") as f:
    yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
PY
}

migrate_sensitive_credentials_to_env() {
  log_info "迁移敏感凭据到 daemon 环境文件: ${NEXTARC_ENV_FILE}"
  log_info "强制将 USTC 认证改为环境变量模式，并清除配置文件中的明文账号密码"
  NEXTARC_ENV_FILE="${NEXTARC_ENV_FILE}" \
  "${NEXTARC_VENV_DIR}/bin/python" - "${NEXTARC_CONFIG_DIR}/config.yaml" <<'PY'
from pathlib import Path
import os
import shlex
import sys

import yaml

config_path = Path(sys.argv[1])
env_path = Path(os.environ["NEXTARC_ENV_FILE"])

with config_path.open("r", encoding="utf-8") as f:
    config = yaml.safe_load(f) or {}

ustc = config.setdefault("ustc", {})
env_username = str(ustc.get("env_username") or "USTC_USERNAME")
env_password = str(ustc.get("env_password") or "USTC_PASSWORD")

feishu = config.get("feishu") or {}
mapping = {
    "app_id": "NEXTARC_FEISHU_APP_ID",
    "app_secret": "NEXTARC_FEISHU_APP_SECRET",
    "open_id": "NEXTARC_FEISHU_OPEN_ID",
    "chat_id": "NEXTARC_FEISHU_CHAT_ID",
    "user_id": "NEXTARC_FEISHU_USER_ID",
}

values: dict[str, str] = {}
if env_path.exists():
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
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

username = ustc.get("username")
password = ustc.get("password")
if username:
    values[env_username] = str(username)
if password:
    values[env_password] = str(password)

if not values.get(env_username) or not values.get(env_password):
    raise SystemExit(
        "旧配置未包含可迁移的 USTC 明文账号密码，且 daemon 环境文件中也没有完整的 "
        f"{env_username}/{env_password}。请先完成初始化或手动补充环境变量。"
    )

ustc["auth_mode"] = "env"
ustc["username"] = ""
ustc["password"] = ""
ustc["env_username"] = env_username
ustc["env_password"] = env_password

for config_key, env_key in mapping.items():
    value = feishu.get(config_key)
    if value:
        values[env_key] = str(value)

env_path.parent.mkdir(parents=True, exist_ok=True)
lines = [
    "# NextArc systemd environment file",
    "# This file contains secrets. Keep permissions restricted.",
]
for key in sorted(values):
    lines.append(f"{key}={shlex.quote(values[key])}")
env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
env_path.chmod(0o640)

with config_path.open("w", encoding="utf-8") as f:
    yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
PY
}

migrate_legacy_data() {
  require_installed_service
  validate_migration_source

  local target_data_dir="${NEXTARC_STATE_DIR}/data"
  local service_was_active="no"
  if systemctl is-active --quiet nextarc; then
    service_was_active="yes"
  fi
  restart_nextarc_on_migration_error() {
    if [[ "${service_was_active}" == "yes" ]]; then
      echo "迁移失败，尝试恢复启动 nextarc 服务。" >&2
      systemctl start nextarc || true
    fi
  }
  trap restart_nextarc_on_migration_error ERR

  log_step "停止 NextArc 服务"
  systemctl stop nextarc || true

  log_step "迁移旧配置和数据"
  log_info "目标配置目录: ${NEXTARC_CONFIG_DIR}"
  log_info "目标数据目录: ${target_data_dir}"
  mkdir -p "${NEXTARC_CONFIG_DIR}" "${target_data_dir}"

  log_info "覆盖主配置文件: config.yaml"
  install -m 0640 -o root -g nextarc "${MIGRATE_SOURCE_DIR}/config/config.yaml" "${NEXTARC_CONFIG_DIR}/config.yaml"
  log_info "覆盖偏好配置文件: preferences.yaml"
  install -m 0640 -o root -g nextarc "${MIGRATE_SOURCE_DIR}/config/preferences.yaml" "${NEXTARC_CONFIG_DIR}/preferences.yaml"

  log_info "覆盖数据库文件"
  find "${target_data_dir}" -maxdepth 1 -type f -name '*.db' -delete
  install -o nextarc -g nextarc -m 0640 "${MIGRATE_DB_FILES[@]}" "${target_data_dir}/"

  rewrite_migrated_config_paths
  migrate_sensitive_credentials_to_env
  fix_permissions

  log_step "重启 NextArc 服务"
  trap - ERR
  systemctl start nextarc

  echo
  echo "NextArc 旧数据迁移完成。"
  echo "已迁移配置: ${NEXTARC_CONFIG_DIR}/config.yaml"
  echo "已迁移偏好: ${NEXTARC_CONFIG_DIR}/preferences.yaml"
  echo "已迁移数据库目录: ${target_data_dir}"
}

install_service() {
  log_step "安装并启动 systemd 服务"
  log_info "写入服务文件: ${NEXTARC_SERVICE_FILE}"
  log_info "服务运行用户: nextarc"
  log_info "工作目录: ${NEXTARC_APP_DIR}"
  log_info "启动命令: ${NEXTARC_VENV_DIR}/bin/nextarc run"
  cat >"${NEXTARC_SERVICE_FILE}" <<EOF
[Unit]
Description=NextArc Feishu Bot
Documentation=https://github.com/Amsors/NextArc
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=nextarc
Group=nextarc
WorkingDirectory=${NEXTARC_APP_DIR}
EnvironmentFile=${NEXTARC_ENV_FILE}
Environment=NEXTARC_CONFIG=${NEXTARC_CONFIG_DIR}/config.yaml
Environment=NEXTARC_PREFERENCES=${NEXTARC_CONFIG_DIR}/preferences.yaml
Environment=NEXTARC_STATE=${NEXTARC_STATE_DIR}/state.yaml
Environment=NEXTARC_STATE_DIR=${NEXTARC_STATE_DIR}
ExecStart=${NEXTARC_VENV_DIR}/bin/nextarc run
Restart=always
RestartSec=10
KillSignal=SIGTERM
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=${NEXTARC_STATE_DIR} ${NEXTARC_LOG_DIR}
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
SystemCallArchitectures=native
CapabilityBoundingSet=

[Install]
WantedBy=multi-user.target
EOF
  log_info "设置服务文件权限为 0644"
  chmod 0644 "${NEXTARC_SERVICE_FILE}"
  log_info "重新加载 systemd 配置"
  systemctl daemon-reload
  log_info "启用并启动升级请求监听: nextarc-upgrade.path"
  systemctl enable --now nextarc-upgrade.path
  log_info "启用并启动服务: nextarc"
  systemctl enable --now nextarc
}

main() {
  parse_args "$@"

  case "${ACTION}" in
    help)
      usage
      exit 0
      ;;
  esac

  require_root
  validate_install_paths

  case "${ACTION}" in
    uninstall)
      uninstall_service
      exit 0
      ;;
    purge)
      purge_all
      exit 0
      ;;
    migrate)
      migrate_legacy_data
      exit 0
      ;;
  esac

  configure_repo_urls
  validate_repo_refs

  log_step "开始安装 NextArc"
  log_info "仓库来源: ${NEXTARC_REPO_ORIGIN}"
  log_info "安装目录: ${NEXTARC_INSTALL_DIR}"
  log_info "应用目录: ${NEXTARC_APP_DIR}"
  log_info "虚拟环境: ${NEXTARC_VENV_DIR}"
  log_info "配置目录: ${NEXTARC_CONFIG_DIR}"
  log_info "状态目录: ${NEXTARC_STATE_DIR}"
  log_info "日志目录: ${NEXTARC_LOG_DIR}"
  log_info "systemd 服务文件: ${NEXTARC_SERVICE_FILE}"

  install_packages
  ensure_user_and_dirs
  checkout_code
  checkout_pyustc
  install_python_deps
  run_bootstrap_if_needed
  fix_permissions
  install_upgrade_service
  install_service

  echo
  echo "NextArc 已安装并启动。"
  echo "查看状态: sudo systemctl status nextarc"
  echo "查看日志: sudo journalctl -u nextarc -f"
  echo "AI 配置: sudo ${NEXTARC_VENV_DIR}/bin/nextarc --ai-config"
  echo "卸载服务: sudo bash install-nextarc.sh --uninstall"
}

main "$@"
