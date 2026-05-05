"""NextArc 命令行入口。"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import grp
import os
import pwd
import shlex
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CONFIG_DIR = Path(os.getenv("NEXTARC_CONFIG_DIR", "/etc/nextarc"))
DEFAULT_STATE_DIR = Path(os.getenv("NEXTARC_STATE_DIR", "/var/lib/nextarc"))
DEFAULT_LOG_DIR = Path(os.getenv("NEXTARC_LOG_DIR", "/var/log/nextarc"))
DEFAULT_CONFIG_PATH = Path(os.getenv("NEXTARC_CONFIG", str(DEFAULT_CONFIG_DIR / "config.yaml")))
DEFAULT_PREFERENCES_PATH = Path(
    os.getenv("NEXTARC_PREFERENCES", str(DEFAULT_CONFIG_DIR / "preferences.yaml"))
)
DEFAULT_ENV_PATH = Path(os.getenv("NEXTARC_ENV_FILE", str(DEFAULT_CONFIG_DIR / "nextarc.env")))
DEFAULT_STATE_PATH = Path(os.getenv("NEXTARC_STATE", str(DEFAULT_STATE_DIR / "state.yaml")))


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _write_yaml(path: Path, data: dict[str, Any], mode: int = 0o640) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    path.chmod(mode)


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
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


def _write_env_file(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# NextArc systemd environment file",
        "# This file contains secrets. Keep permissions restricted.",
    ]
    for key in sorted(values):
        lines.append(f"{key}={_shell_quote(values[key])}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o640)


def _set_nested(data: dict[str, Any], keys: list[str], value: Any) -> None:
    current = data
    for key in keys[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    current[keys[-1]] = value


def _load_config_template() -> dict[str, Any]:
    template_path = PROJECT_ROOT / "config" / "config.example.yaml"
    data = _load_yaml(template_path)
    if not data:
        raise RuntimeError(f"无法读取配置模板: {template_path}")
    return data


def _load_preferences_template() -> dict[str, Any]:
    template_path = PROJECT_ROOT / "config" / "preferences.example.yaml"
    data = _load_yaml(template_path)
    if not data:
        return {"version": "1.0", "time_filter": {"enabled": False}}
    return data


def _chown_for_nextarc(paths: list[Path]) -> None:
    if os.geteuid() != 0:
        return
    try:
        uid = pwd.getpwnam("nextarc").pw_uid
        gid = grp.getgrnam("nextarc").gr_gid
    except KeyError:
        return

    for path in paths:
        if not path.exists():
            continue
        if path.is_dir():
            for root, dirs, files in os.walk(path):
                os.chown(root, uid, gid)
                for name in dirs + files:
                    os.chown(Path(root) / name, uid, gid)
        else:
            os.chown(path, uid, gid)


def _chown_config_for_nextarc(paths: list[Path]) -> None:
    if os.geteuid() != 0:
        return
    try:
        gid = grp.getgrnam("nextarc").gr_gid
    except KeyError:
        return

    for path in paths:
        if path.exists():
            os.chown(path, 0, gid)


def _prepare_base_config() -> dict[str, Any]:
    config = _load_config_template()
    _set_nested(config, ["ustc", "auth_mode"], "env")
    _set_nested(config, ["database", "data_dir"], str(DEFAULT_STATE_DIR / "data"))
    _set_nested(config, ["database", "preference_db_path"], str(DEFAULT_STATE_DIR / "data" / "user_preference.db"))
    _set_nested(config, ["logging", "file", "enabled"], False)
    _set_nested(config, ["logging", "file", "path"], str(DEFAULT_LOG_DIR / "nextarc.log"))
    _set_nested(config, ["version_check", "enabled"], False)
    _set_nested(config, ["ai", "enabled"], False)
    _set_nested(config, ["monitor", "use_ai_filter"], False)
    _set_nested(config, ["feishu", "app_id"], "")
    _set_nested(config, ["feishu", "app_secret"], "")
    _set_nested(config, ["feishu", "open_id"], "")
    _set_nested(config, ["feishu", "chat_id"], "")
    _set_nested(config, ["feishu", "user_id"], "")
    return config


def _write_state(open_id: str = "", chat_id: str = "", user_id: str = "") -> None:
    state = _load_yaml(DEFAULT_STATE_PATH)
    if open_id:
        state["feishu_open_id"] = open_id
    if chat_id:
        state["feishu_chat_id"] = chat_id
    if user_id:
        state["feishu_user_id"] = user_id
    _write_yaml(DEFAULT_STATE_PATH, state, mode=0o600)


def _register_feishu() -> tuple[str, str, str]:
    try:
        import lark_oapi as lark
    except ImportError as exc:
        raise RuntimeError("未安装 lark-oapi，请先安装依赖") from exc

    if not hasattr(lark, "register_app"):
        raise RuntimeError("当前 lark-oapi 版本不支持 register_app，请升级到 1.5.5 或更高版本")

    def on_qr_code(info: dict[str, Any]) -> None:
        print()
        print("请使用飞书扫码或在浏览器打开以下链接完成应用创建：")
        print(info["url"])
        print(f"链接有效期约 {info.get('expire_in', 600)} 秒")
        print()

    def on_status_change(info: dict[str, Any]) -> None:
        status = info.get("status")
        if status == "polling":
            print("等待飞书授权确认...")
        elif status == "slow_down":
            print(f"飞书要求降低轮询频率，当前间隔 {info.get('interval')} 秒")
        elif status == "domain_switched":
            print("已切换到 Lark 国际版认证域")

    result = lark.register_app(
        on_qr_code=on_qr_code,
        on_status_change=on_status_change,
        source="nextarc",
    )
    app_id = result["client_id"]
    app_secret = result["client_secret"]
    open_id = (result.get("user_info") or {}).get("open_id", "")
    return app_id, app_secret, open_id


def cmd_bootstrap(_args: argparse.Namespace) -> int:
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_STATE_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)

    print("NextArc 初始化")
    username = input("请输入 USTC 学号: ").strip()
    password = getpass.getpass("请输入 USTC 统一身份认证密码: ").strip()
    if not username or not password:
        print("USTC 学号和密码不能为空", file=sys.stderr)
        return 1

    app_id, app_secret, open_id = _register_feishu()
    if not open_id:
        print("警告：飞书未返回 open_id，首次启动可能需要先给机器人发送消息")

    config = _prepare_base_config()
    preferences = _load_preferences_template()
    _write_yaml(DEFAULT_CONFIG_PATH, config)
    _write_yaml(DEFAULT_PREFERENCES_PATH, preferences)

    env_values = _read_env_file(DEFAULT_ENV_PATH)
    env_values.update(
        {
            "USTC_USERNAME": username,
            "USTC_PASSWORD": password,
            "NEXTARC_FEISHU_APP_ID": app_id,
            "NEXTARC_FEISHU_APP_SECRET": app_secret,
            "NEXTARC_FEISHU_OPEN_ID": open_id,
            "NEXTARC_CONFIG": str(DEFAULT_CONFIG_PATH),
            "NEXTARC_PREFERENCES": str(DEFAULT_PREFERENCES_PATH),
            "NEXTARC_STATE": str(DEFAULT_STATE_PATH),
            "NEXTARC_STATE_DIR": str(DEFAULT_STATE_DIR),
        }
    )
    _write_env_file(DEFAULT_ENV_PATH, env_values)
    _write_state(open_id=open_id)
    _chown_config_for_nextarc([DEFAULT_CONFIG_DIR, DEFAULT_CONFIG_PATH, DEFAULT_PREFERENCES_PATH, DEFAULT_ENV_PATH])
    _chown_for_nextarc([DEFAULT_STATE_DIR, DEFAULT_LOG_DIR])

    print()
    print("初始化完成")
    print(f"配置文件: {DEFAULT_CONFIG_PATH}")
    print(f"敏感环境变量: {DEFAULT_ENV_PATH}")
    print(f"运行态状态: {DEFAULT_STATE_PATH}")
    return 0


def cmd_feishu_register(_args: argparse.Namespace) -> int:
    app_id, app_secret, open_id = _register_feishu()
    env_values = _read_env_file(DEFAULT_ENV_PATH)
    env_values.update(
        {
            "NEXTARC_FEISHU_APP_ID": app_id,
            "NEXTARC_FEISHU_APP_SECRET": app_secret,
            "NEXTARC_FEISHU_OPEN_ID": open_id,
        }
    )
    _write_env_file(DEFAULT_ENV_PATH, env_values)
    _write_state(open_id=open_id)
    _chown_config_for_nextarc([DEFAULT_CONFIG_DIR, DEFAULT_ENV_PATH])
    _chown_for_nextarc([DEFAULT_STATE_DIR])
    print("飞书应用凭据已更新")
    return 0


def cmd_ai_config(_args: argparse.Namespace) -> int:
    config = _load_yaml(DEFAULT_CONFIG_PATH)
    if not config:
        config = _prepare_base_config()

    print("NextArc AI 筛选配置")
    enabled = input("是否启用 AI 筛选？[y/N]: ").strip().lower() == "y"
    _set_nested(config, ["ai", "enabled"], enabled)
    _set_nested(config, ["monitor", "use_ai_filter"], enabled)

    env_values = _read_env_file(DEFAULT_ENV_PATH)
    if enabled:
        api_key = getpass.getpass("请输入 AI API Key: ").strip()
        base_url = input("请输入 API Base URL（可留空使用默认）: ").strip()
        model = input("请输入模型名称: ").strip()
        temperature_raw = input("请输入 temperature（默认 0.3）: ").strip() or "0.3"
        user_info = input("请简要描述你的活动偏好: ").strip()

        try:
            temperature = float(temperature_raw)
        except ValueError:
            print("temperature 必须是数字", file=sys.stderr)
            return 1

        env_values["NEXTARC_AI_API_KEY"] = api_key
        _set_nested(config, ["ai", "base_url"], base_url)
        _set_nested(config, ["ai", "model"], model)
        _set_nested(config, ["ai", "temperature"], temperature)
        _set_nested(config, ["ai", "user_info"], user_info)
    else:
        env_values.pop("NEXTARC_AI_API_KEY", None)

    _write_yaml(DEFAULT_CONFIG_PATH, config)
    _write_env_file(DEFAULT_ENV_PATH, env_values)
    _chown_config_for_nextarc([DEFAULT_CONFIG_DIR, DEFAULT_CONFIG_PATH, DEFAULT_ENV_PATH])
    print("AI 配置已更新。请重启 nextarc 服务使配置生效。")
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    checks = [
        ("配置文件", DEFAULT_CONFIG_PATH.exists(), str(DEFAULT_CONFIG_PATH)),
        ("偏好配置", DEFAULT_PREFERENCES_PATH.exists(), str(DEFAULT_PREFERENCES_PATH)),
        ("环境变量文件", DEFAULT_ENV_PATH.exists(), str(DEFAULT_ENV_PATH)),
        ("运行态状态", DEFAULT_STATE_PATH.exists(), str(DEFAULT_STATE_PATH)),
        ("项目依赖", shutil.which("python") is not None, sys.executable),
    ]

    failed = False
    for name, ok, detail in checks:
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {name}: {detail}")
        failed = failed or not ok

    try:
        import lark_oapi as lark
        has_register = hasattr(lark, "register_app")
        print(f"[{'OK' if has_register else 'FAIL'}] lark-oapi register_app: {has_register}")
        failed = failed or not has_register
    except ImportError:
        print("[FAIL] lark-oapi: 未安装")
        failed = True

    return 1 if failed else 0


def cmd_run(_args: argparse.Namespace) -> int:
    from src.main import main

    asyncio.run(main())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nextarc")
    parser.add_argument("--ai-config", action="store_true", help="交互式配置 AI 筛选")
    parser.add_argument("--feishu-register", action="store_true", help="重新注册飞书应用")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("run", help="启动 NextArc 服务")
    subparsers.add_parser("bootstrap", help="初始化配置和飞书应用")
    subparsers.add_parser("feishu-register", help="重新注册飞书应用")
    subparsers.add_parser("ai-config", help="交互式配置 AI 筛选")
    subparsers.add_parser("doctor", help="检查部署状态")
    return parser


def main_cli() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.ai_config:
        return cmd_ai_config(args)
    if args.feishu_register:
        return cmd_feishu_register(args)

    match args.command:
        case "run":
            return cmd_run(args)
        case "bootstrap":
            return cmd_bootstrap(args)
        case "feishu-register":
            return cmd_feishu_register(args)
        case "ai-config":
            return cmd_ai_config(args)
        case "doctor":
            return cmd_doctor(args)
        case _:
            parser.print_help()
            return 1


if __name__ == "__main__":
    raise SystemExit(main_cli())
