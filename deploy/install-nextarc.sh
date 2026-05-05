#!/usr/bin/env bash
set -Eeuo pipefail

NEXTARC_REPO_URL="${NEXTARC_REPO_URL:-https://github.com/Amsors/NextArc}"
NEXTARC_REPO_BRANCH="${NEXTARC_REPO_BRANCH:-feat/one_click_deploy}"
PYUSTC_REPO_URL="${PYUSTC_REPO_URL:-https://github.com/Amsors/pyustc}"
PYUSTC_REPO_BRANCH="${PYUSTC_REPO_BRANCH:-adapt/NextArc}"

NEXTARC_INSTALL_DIR="${NEXTARC_INSTALL_DIR:-/opt/nextarc}"
NEXTARC_APP_DIR="${NEXTARC_APP_DIR:-/opt/nextarc/app}"
NEXTARC_VENV_DIR="${NEXTARC_VENV_DIR:-/opt/nextarc/venv}"
NEXTARC_CONFIG_DIR="${NEXTARC_CONFIG_DIR:-/etc/nextarc}"
NEXTARC_STATE_DIR="${NEXTARC_STATE_DIR:-/var/lib/nextarc}"
NEXTARC_LOG_DIR="${NEXTARC_LOG_DIR:-/var/log/nextarc}"
NEXTARC_ENV_FILE="${NEXTARC_ENV_FILE:-/etc/nextarc/nextarc.env}"
NEXTARC_SERVICE_FILE="/etc/systemd/system/nextarc.service"

usage() {
  cat <<'EOF'
Usage:
  install-nextarc.sh
  install-nextarc.sh --uninstall
  install-nextarc.sh --purge

Environment overrides:
  NEXTARC_REPO_URL
  NEXTARC_REPO_BRANCH
  PYUSTC_REPO_URL
  PYUSTC_REPO_BRANCH
EOF
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "请使用 root 权限运行，例如：sudo bash install-nextarc.sh" >&2
    exit 1
  fi
}

uninstall_service() {
  systemctl disable --now nextarc >/dev/null 2>&1 || true
  rm -f "${NEXTARC_SERVICE_FILE}"
  systemctl daemon-reload
  systemctl reset-failed nextarc >/dev/null 2>&1 || true
  echo "NextArc systemd 服务已卸载。配置、数据、日志和代码均已保留。"
}

purge_all() {
  uninstall_service
  echo
  echo "危险操作：这将删除 NextArc 代码、配置、飞书凭据、USTC 凭据、数据和日志。"
  read -r -p "如确认删除，请输入 DELETE NEXTARC: " confirmation
  if [[ "${confirmation}" != "DELETE NEXTARC" ]]; then
    echo "已取消彻底卸载。"
    exit 1
  fi
  rm -rf "${NEXTARC_INSTALL_DIR}" "${NEXTARC_CONFIG_DIR}" "${NEXTARC_STATE_DIR}" "${NEXTARC_LOG_DIR}"
  userdel nextarc >/dev/null 2>&1 || true
  echo "NextArc 已彻底卸载。"
}

install_packages() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y git curl ca-certificates python3 python3-venv python3-pip sqlite3
}

ensure_user_and_dirs() {
  if ! id nextarc >/dev/null 2>&1; then
    useradd --system --home "${NEXTARC_STATE_DIR}" --shell /usr/sbin/nologin nextarc
  fi

  mkdir -p "${NEXTARC_INSTALL_DIR}" "${NEXTARC_CONFIG_DIR}" "${NEXTARC_STATE_DIR}" "${NEXTARC_LOG_DIR}"
  chown -R nextarc:nextarc "${NEXTARC_STATE_DIR}" "${NEXTARC_LOG_DIR}"
  chmod 750 "${NEXTARC_CONFIG_DIR}" "${NEXTARC_STATE_DIR}" "${NEXTARC_LOG_DIR}"
}

checkout_code() {
  if [[ -d "${NEXTARC_APP_DIR}/.git" ]]; then
    git -C "${NEXTARC_APP_DIR}" fetch origin "${NEXTARC_REPO_BRANCH}"
    git -C "${NEXTARC_APP_DIR}" checkout "${NEXTARC_REPO_BRANCH}"
    git -C "${NEXTARC_APP_DIR}" pull --ff-only origin "${NEXTARC_REPO_BRANCH}"
  else
    rm -rf "${NEXTARC_APP_DIR}"
    git clone --branch "${NEXTARC_REPO_BRANCH}" --single-branch "${NEXTARC_REPO_URL}" "${NEXTARC_APP_DIR}"
  fi
}

install_python_deps() {
  local pyustc_pip_url="${PYUSTC_REPO_URL}"
  if [[ "${pyustc_pip_url}" != *.git ]]; then
    pyustc_pip_url="${pyustc_pip_url}.git"
  fi

  python3 -m venv "${NEXTARC_VENV_DIR}"
  "${NEXTARC_VENV_DIR}/bin/python" -m pip install --upgrade pip wheel
  "${NEXTARC_VENV_DIR}/bin/pip" install -r "${NEXTARC_APP_DIR}/requirements.txt"
  "${NEXTARC_VENV_DIR}/bin/pip" install "git+${pyustc_pip_url}@${PYUSTC_REPO_BRANCH}"

  cat >"${NEXTARC_VENV_DIR}/bin/nextarc" <<EOF
#!/usr/bin/env bash
cd "${NEXTARC_APP_DIR}"
exec "${NEXTARC_VENV_DIR}/bin/python" -m src.cli "\$@"
EOF
  chmod 755 "${NEXTARC_VENV_DIR}/bin/nextarc"
}

run_bootstrap_if_needed() {
  if [[ -f "${NEXTARC_ENV_FILE}" && -f "${NEXTARC_CONFIG_DIR}/config.yaml" ]]; then
    echo "检测到已有配置，跳过初始化向导。"
    return
  fi

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
  chown -R root:root "${NEXTARC_INSTALL_DIR}"
  chown -R root:nextarc "${NEXTARC_CONFIG_DIR}"
  chown -R nextarc:nextarc "${NEXTARC_STATE_DIR}" "${NEXTARC_LOG_DIR}"
  chmod 750 "${NEXTARC_CONFIG_DIR}" "${NEXTARC_STATE_DIR}" "${NEXTARC_LOG_DIR}"
  [[ -f "${NEXTARC_ENV_FILE}" ]] && chmod 640 "${NEXTARC_ENV_FILE}"
}

install_service() {
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
  chmod 0644 "${NEXTARC_SERVICE_FILE}"
  systemctl daemon-reload
  systemctl enable --now nextarc
}

main() {
  require_root

  case "${1:-}" in
    -h|--help)
      usage
      exit 0
      ;;
    --uninstall)
      uninstall_service
      exit 0
      ;;
    --purge)
      purge_all
      exit 0
      ;;
    "")
      ;;
    *)
      usage >&2
      exit 1
      ;;
  esac

  install_packages
  ensure_user_and_dirs
  checkout_code
  install_python_deps
  run_bootstrap_if_needed
  fix_permissions
  install_service

  echo
  echo "NextArc 已安装并启动。"
  echo "查看状态: sudo systemctl status nextarc"
  echo "查看日志: sudo journalctl -u nextarc -f"
  echo "AI 配置: sudo ${NEXTARC_VENV_DIR}/bin/nextarc --ai-config"
  echo "卸载服务: sudo bash install-nextarc.sh --uninstall"
}

main "$@"
