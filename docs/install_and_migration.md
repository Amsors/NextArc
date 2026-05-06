# NextArc 安装、迁移与升级脚本文档

本文说明 `deploy/install-nextarc.sh` 和 `deploy/upgrade-nextarc.sh` 的用法、参数和执行行为。

`install-nextarc.sh` 是用户直接运行的一键安装和迁移入口。

`upgrade-nextarc.sh` 是服务化安装后由 systemd 或机器人 `/upgrade` 指令触发的后台升级脚本，通常**不需要**手动运行。

## 适用环境

- 支持 systemd 的 Linux 服务器。
- 需要 root 权限运行安装、迁移、卸载和升级流程。
- 安装脚本使用 `apt-get` 安装系统依赖，当前主要面向 Debian/Ubuntu 系发行版（我校Vlab提供的机器即为Ubuntu）。
- 服务器需要能访问所选 Git 仓库和 Python 包索引（当前默认通过校内gitlab获取代码，无需访问github）。

默认安装完成后，NextArc 会以 `nextarc` 系统用户运行，配置、数据和日志分别放在 `/etc/nextarc`、`/var/lib/nextarc` 和 `/var/log/nextarc`。

## 快速安装

在终端中执行：

```bash
【待补充】
```

默认行为：

1. 使用 LUG 校内 GitLab 镜像作为 NextArc 和 pyustc 代码来源。
2. 安装系统依赖：`git`、`curl`、`ca-certificates`、`python3`、`python3-venv`、`python3-pip`、`sqlite3`。
3. 创建 `nextarc` 系统用户。
4. 创建安装、配置、状态和日志目录。
5. 拉取 NextArc 与 pyustc 代码。
6. 创建 Python 虚拟环境并安装依赖。
7. 运行交互式初始化向导，写入配置和敏感环境变量。
8. 安装 `nextarc.service`、`nextarc-upgrade.service` 和 `nextarc-upgrade.path`。
9. 启用并启动 NextArc 服务和升级请求监听。

安装完成后常用命令：

```bash
sudo systemctl status nextarc # 查看机器人服务状态
sudo journalctl -u nextarc -f # 查看机器人日志
sudo /opt/nextarc/venv/bin/nextarc ai-config # 配置ai筛选【后续考虑将nextarc写入PATH】
```

## 安装脚本参数

### `--origin github` 或 `--origin lug_gitlab`

选择 NextArc 和 pyustc 的代码来源：

```bash
sudo bash deploy/install-nextarc.sh --origin lug_gitlab
sudo bash deploy/install-nextarc.sh --origin github
```

默认值是 `lug_gitlab`。

- `lug_gitlab`：使用校内 LUG GitLab 镜像，适合校内网络或访问 GitHub 不稳定的环境。
- `github`：使用 GitHub 上游仓库。

一般而言我会保持这两个仓库的同步更新。

如果同时人为设置了 `NEXTARC_REPO_URL` 或 `PYUSTC_REPO_URL`，自定义 URL 会覆盖 `--origin` 对应的默认仓库地址。

---

### `--skip-feishu-register` / `--skip-feishu`

安装时跳过飞书应用创建：

```bash
sudo bash deploy/install-nextarc.sh --skip-feishu-register
```

脚本仍会创建配置文件和环境文件，但飞书 `app_id`、`app_secret`、`open_id` 为空。之后可以通过以下方式补充飞书配置：

```bash
sudo /opt/nextarc/venv/bin/nextarc feishu-register
```

也可以在迁移旧部署时，让迁移流程把旧配置中的飞书凭据转入 daemon 环境文件。

---

### `--migrate /path/to/old_nextarc` 

将旧版手动部署目录中的配置和数据库迁移到服务化安装：

```bash
sudo bash deploy/install-nextarc.sh --migrate /home/you/NextArc
```

或使用等价写法：

```bash
sudo bash deploy/install-nextarc.sh --migrate=/home/you/NextArc
```

**迁移前必须已经完成一次服务化安装**，因为脚本会检查以下内容是否存在：

- `/etc/systemd/system/nextarc.service`
- NextArc 应用目录
- 配置目录
- 状态目录
- Python 虚拟环境
- `nextarc` 系统用户

旧目录必须包含：

- `config/config.yaml`
- `config/preferences.yaml`
- `data/` 目录
- 至少一个 `data/*.db` 数据库文件

迁移行为：

1. 如果 `nextarc` 服务正在运行，先停止服务。
2. 用旧部署的 `config/config.yaml` 覆盖 `/etc/nextarc/config.yaml`。
3. 用旧部署的 `config/preferences.yaml` 覆盖 `/etc/nextarc/preferences.yaml`。
4. 删除目标数据目录中已有的 `.db` 文件。
5. 将旧部署 `data/*.db` 复制到 `/var/lib/nextarc/data/`。
6. 将配置中的数据库路径改写为 daemon 布局：
   - `database.data_dir` 改为 `/var/lib/nextarc/data`
   - `database.preference_db_path` 改为 `/var/lib/nextarc/data/user_preference.db`
7. 将旧配置中的 USTC 明文学号和密码迁移到 `/etc/nextarc/nextarc.env`。
8. 将 `ustc.auth_mode` 强制改为 `env`，并清空配置文件中的明文学号和密码。
9. 将旧配置中的飞书凭据迁移到 `/etc/nextarc/nextarc.env`。
10. 修正文件所有者和权限。
11. 重新启动 `nextarc` 服务。

如果迁移失败且迁移前服务处于运行状态，脚本会尝试重新启动原服务。

注意：迁移会覆盖 daemon 安装中的主配置、偏好配置和目标数据目录下的 `.db` 文件。执行前建议自行备份 `/etc/nextarc` 和 `/var/lib/nextarc`。

---

### `--uninstall`

卸载 systemd 服务，但保留代码、配置、数据和日志：

```bash
sudo bash deploy/install-nextarc.sh --uninstall
```

脚本会：

- 停止并禁用 `nextarc.service`。
- 停止并禁用 `nextarc-upgrade.path`。
- 停止 `nextarc-upgrade.service`。
- 删除 systemd 服务文件和升级脚本。
- 删除旧版 sudoers 白名单文件。
- 执行 `systemctl daemon-reload` 并清理 failed 状态。

不会删除：

- `/opt/nextarc`
- `/etc/nextarc`
- `/var/lib/nextarc`
- `/var/log/nextarc`

---

### `--purge`

**彻底卸载** NextArc：

```bash
sudo bash deploy/install-nextarc.sh --purge
```

脚本会先执行 `--uninstall` 的服务卸载流程，然后要求输入：

```text
DELETE NEXTARC
```

确认后会删除：

- `/opt/nextarc`
- `/etc/nextarc`
- `/var/lib/nextarc`
- `/var/log/nextarc`
- `/usr/local/lib/nextarc`
- `nextarc` 系统用户

该操作会删除 USTC 凭据、飞书凭据、配置、数据库和日志，不能通过脚本恢复。

---

### `-h` / `--help`

显示安装脚本帮助：

```bash
bash deploy/install-nextarc.sh --help
```

## 安装脚本环境变量

安装脚本支持用环境变量覆盖默认路径、仓库和分支。示例：

```bash
sudo env NEXTARC_REPO_BRANCH=main bash deploy/install-nextarc.sh --origin github
```

可用变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `NEXTARC_REPO_ORIGIN` | `lug_gitlab` | 默认仓库来源，可被 `--origin` 覆盖 |
| `NEXTARC_REPO_URL` | 由仓库来源决定 | NextArc 仓库 URL |
| `NEXTARC_REPO_BRANCH` | `feat/one_click_deploy` | NextArc 安装分支 |
| `PYUSTC_REPO_URL` | 由仓库来源决定 | pyustc 仓库 URL |
| `PYUSTC_REPO_BRANCH` | `adapt/NextArc` | pyustc 安装分支 |
| `NEXTARC_INSTALL_DIR` | `/opt/nextarc` | 安装根目录 |
| `NEXTARC_APP_DIR` | `/opt/nextarc/app` | NextArc 代码目录，必须位于安装根目录下 |
| `NEXTARC_PYUSTC_DIR` | `/opt/nextarc/pyustc` | pyustc 代码目录，必须位于安装根目录下 |
| `NEXTARC_VENV_DIR` | `/opt/nextarc/venv` | Python 虚拟环境目录，必须位于安装根目录下 |
| `NEXTARC_CONFIG_DIR` | `/etc/nextarc` | 配置目录 |
| `NEXTARC_STATE_DIR` | `/var/lib/nextarc` | 状态和数据库目录 |
| `NEXTARC_LOG_DIR` | `/var/log/nextarc` | 日志目录 |
| `NEXTARC_ENV_FILE` | `/etc/nextarc/nextarc.env` | systemd 环境变量文件，必须位于配置目录下 |
| `NEXTARC_LIB_DIR` | `/usr/local/lib/nextarc` | 维护脚本目录 |

路径变量必须满足脚本的安全检查：

- 必须是绝对路径。
- 不能包含空白字符、`.` 或 `..` 路径组件。
- 不能是符号链接。
- 不能指向 `/`、`/etc`、`/var`、`/usr`、`/opt` 等系统关键目录本身。
- `NEXTARC_APP_DIR`、`NEXTARC_PYUSTC_DIR` 和 `NEXTARC_VENV_DIR` 必须位于 `NEXTARC_INSTALL_DIR` 下。
- `NEXTARC_ENV_FILE` 必须位于 `NEXTARC_CONFIG_DIR` 下。

分支变量必须是安全的 git ref，不能以 `-` 开头，不能包含 `..`，不能以 `.lock` 结尾，只能包含字母、数字、点、下划线、斜杠和短横线。

## 安装后的目录和权限

默认安装布局：

| 路径 | 用途 | 权限/所有者 |
|------|------|-------------|
| `/opt/nextarc/app` | NextArc 代码 | `root:root` |
| `/opt/nextarc/pyustc` | pyustc 代码 | `root:root` |
| `彻底卸载/opt/nextarc/venv` | Python 虚拟环境 | `root:root` |
| `/etc/nextarc` | 配置和敏感环境变量 | `root:nextarc`，目录 `750` |
| `/etc/nextarc/nextarc.env` | USTC、飞书、AI 等敏感环境变量 | `640` |
| `/var/lib/nextarc` | 运行状态、数据库、升级请求和状态 | `nextarc:nextarc`，目录 `750` |
| `/var/log/nextarc` | 日志目录 | `nextarc:nextarc`，目录 `750` |
| `/usr/local/lib/nextarc/upgrade-nextarc.sh` | 后台升级脚本 | root 安装 |

`nextarc.service` 使用 `ProtectSystem=strict`、`NoNewPrivileges=true` 等 systemd 限制，只允许写入状态和日志目录。

## 自升级脚本行为

`deploy/upgrade-nextarc.sh` 会被安装到：

```text
/usr/local/lib/nextarc/upgrade-nextarc.sh
```

服务化安装会创建：

- `nextarc-upgrade.service`
- `nextarc-upgrade.path`

机器人中发送 `/upgrade` 并确认后，应用会写入：

```text
/var/lib/nextarc/upgrade-request.env
```

`nextarc-upgrade.path` 监听到该文件后触发 `nextarc-upgrade.service`，以 root 运行升级脚本。

升级请求文件只允许包含：

- `NEXTARC_UPGRADE_REMOTE`
- `NEXTARC_UPGRADE_BRANCH`
- `NEXTARC_OLD_VERSION`

升级脚本会检查请求文件安全性：

- 文件必须存在且不能是符号链接。
- owner 和 group 必须是 `nextarc` 用户。
- 权限必须是 `600`。
- 硬链接数量必须是 `1`。
- 远程仓库名、分支名和版本号必须符合安全格式。

升级流程：

1. 校验路径、root 权限和 `nextarc` 用户。
2. 对 `/var/lib/nextarc/upgrade.lock` 加锁，避免并发升级。
3. 读取并校验升级请求。
4. 检查 NextArc 和 pyustc 都是 git 仓库。
5. 检查 NextArc 工作区、暂存区和未跟踪文件均为空。
6. 检查 pyustc 没有跟踪文件改动，并且当前分支配置了上游。
7. 写入升级状态为 `running`。
8. 停止 `nextarc` 服务。
9. 临时把代码目录和虚拟环境所有权交给 `nextarc` 低权限用户。
10. 以 `nextarc` 用户拉取 NextArc 目标远程分支。
11. 以 `nextarc` 用户对 pyustc 执行 `pull --ff-only`。
12. 在虚拟环境中重新安装 NextArc 依赖和 pyustc。
13. 执行 `python -m compileall` 和 `pip check`。
14. 收回目录所有权。
15. 写入升级标记 `/var/lib/nextarc/.next_arc_updated`。
16. 删除升级请求文件。
17. 启动 `nextarc` 服务。
18. 写入升级状态为 `succeeded`。

升级状态文件：

```text
/var/lib/nextarc/upgrade-status.env
```

其中包含：

- `NEXTARC_UPGRADE_STATUS`
- `NEXTARC_UPGRADE_MESSAGE`
- `NEXTARC_UPGRADE_TIME`

如果升级失败，脚本会：

- 恢复目录权限。
- 删除升级请求文件。
- 写入状态为 `failed`。
- 尝试通过飞书发送失败通知。
- 停止 `nextarc` 服务，避免继续运行不确定状态的代码。

查看升级日志：

```bash
sudo journalctl -u nextarc-upgrade -n 100
```

## 手动触发升级脚本

一般不建议手动运行 `upgrade-nextarc.sh`。如果确实需要手动调试，应先以 `nextarc` 用户身份创建合法的升级请求文件，并确保权限为 `600`：

```bash
sudo -u nextarc sh -c 'cat > /var/lib/nextarc/upgrade-request.env <<EOF
NEXTARC_UPGRADE_REMOTE=origin
NEXTARC_UPGRADE_BRANCH=main
NEXTARC_OLD_VERSION=
EOF
chmod 600 /var/lib/nextarc/upgrade-request.env'

sudo systemctl start nextarc-upgrade.service
```

更推荐通过机器人 `/upgrade` 指令触发，因为应用会根据配置中的 `version_check.remote_name` 和 `version_check.branch_name` 写入请求文件。

## 常见操作

### 查看服务状态

```bash
sudo systemctl status nextarc
```

### 查看运行日志

```bash
sudo journalctl -u nextarc -f
```

### 重启服务

```bash
sudo systemctl restart nextarc
```

### 重新配置飞书应用

```bash
sudo /opt/nextarc/venv/bin/nextarc feishu-register
sudo systemctl restart nextarc
```

### 配置 AI 筛选

```bash
sudo /opt/nextarc/venv/bin/nextarc ai-config
sudo systemctl restart nextarc
```

### 检查部署状态

```bash
sudo /opt/nextarc/venv/bin/nextarc doctor
```

## 注意事项

- `--migrate` 会覆盖 daemon 安装中的配置和 `.db` 数据库文件，执行前建议备份。
- `--purge` 会删除所有配置、凭据、数据库和日志。
- 不要手动放宽 `/etc/nextarc/nextarc.env` 权限，该文件包含 USTC 密码、飞书密钥和可能的 AI API Key。
- 自动升级要求 git 工作区干净。**请不要对机器人的代码进行任何修改**。安装目录中的手动改动会导致升级脚本拒绝执行。
- 如果使用了自定义安装路径，安装、迁移、卸载和升级时都**必须**使用同一组路径环境变量。
