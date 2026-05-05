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
  install-nextarc.sh [--origin github|lug_gitlab]
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
Environment=NEXTARC_APP_DIR=${NEXTARC_APP_DIR}
Environment=NEXTARC_INSTALL_DIR=${NEXTARC_INSTALL_DIR}
Environment=NEXTARC_PYUSTC_DIR=${NEXTARC_PYUSTC_DIR}
Environment=NEXTARC_VENV_DIR=${NEXTARC_VENV_DIR}
Environment=NEXTARC_CONFIG_DIR=${NEXTARC_CONFIG_DIR}
Environment=NEXTARC_STATE_DIR=${NEXTARC_STATE_DIR}
Environment=NEXTARC_LOG_DIR=${NEXTARC_LOG_DIR}
ExecStart=${NEXTARC_UPGRADE_SCRIPT}
TimeoutStartSec=900
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
  NEXTARC_CONFIG_DIR="${NEXTARC_CONFIG_DIR}" \
  NEXTARC_STATE_DIR="${NEXTARC_STATE_DIR}" \
  NEXTARC_LOG_DIR="${NEXTARC_LOG_DIR}" \
  NEXTARC_ENV_FILE="${NEXTARC_ENV_FILE}" \
  NEXTARC_CONFIG="${NEXTARC_CONFIG_DIR}/config.yaml" \
  NEXTARC_PREFERENCES="${NEXTARC_CONFIG_DIR}/preferences.yaml" \
  NEXTARC_STATE="${NEXTARC_STATE_DIR}/state.yaml" \
    "${NEXTARC_VENV_DIR}/bin/nextarc" bootstrap
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
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=${NEXTARC_STATE_DIR} ${NEXTARC_LOG_DIR} ${NEXTARC_CONFIG_DIR}

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

  case "${ACTION}" in
    uninstall)
      uninstall_service
      exit 0
      ;;
    purge)
      purge_all
      exit 0
      ;;
  esac

  configure_repo_urls

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
