"""NextArc 命令行入口。"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import grp
import json
import os
import pwd
import shlex
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen

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
FEISHU_REGISTRATION_DOMAIN = os.getenv("NEXTARC_FEISHU_REGISTRATION_DOMAIN", "https://accounts.feishu.cn")
LARK_REGISTRATION_DOMAIN = os.getenv("NEXTARC_LARK_REGISTRATION_DOMAIN", "https://accounts.larksuite.com")
REGISTRATION_ENDPOINT = "/oauth/v1/app/registration"
REGISTRATION_SOURCE = "python-sdk/nextarc"
DEFAULT_REGISTRATION_POLL_INTERVAL = 10.0


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


def _get_nested(data: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _prompt_text(prompt: str, current: str = "", *, required: bool = False) -> str:
    suffix = f" [{current}]" if current else ""
    while True:
        value = input(f"{prompt}{suffix}: ").strip()
        if value:
            return value
        if current:
            return current
        if not required:
            return ""
        print("该项不能为空")


def _prompt_float(prompt: str, current: float | None, *, default: float, minimum: float | None = None,
                  maximum: float | None = None) -> float:
    current_display = str(current if current is not None else default)
    while True:
        raw = input(f"{prompt} [{current_display}]: ").strip()
        value_raw = raw or current_display
        try:
            value = float(value_raw)
        except ValueError:
            print("请输入数字")
            continue
        if minimum is not None and value < minimum:
            print(f"数值不能小于 {minimum}")
            continue
        if maximum is not None and value > maximum:
            print(f"数值不能大于 {maximum}")
            continue
        return value


def _prompt_bool(prompt: str, current: bool = False) -> bool:
    default = "Y/n" if current else "y/N"
    while True:
        raw = input(f"{prompt} [{default}]: ").strip().lower()
        if not raw:
            return current
        if raw in {"y", "yes", "是", "启用", "true", "1"}:
            return True
        if raw in {"n", "no", "否", "禁用", "false", "0"}:
            return False
        print("请输入 y 或 n")


def _prompt_multiline(prompt: str, current: str = "", *, required: bool = False) -> str:
    if current:
        print(f"{prompt}（直接回车保留当前内容；输入多行后用单独一行 . 结束）")
        print("当前内容：")
        print(current)
    else:
        print(f"{prompt}（输入多行后用单独一行 . 结束）")

    first_line = input("> ")
    if not first_line and current:
        return current

    lines: list[str] = []
    if first_line != ".":
        lines.append(first_line)
    while first_line != ".":
        line = input("> ")
        if line == ".":
            break
        lines.append(line)

    value = "\n".join(lines).strip()
    if required and not value:
        print("该项不能为空")
        return _prompt_multiline(prompt, current, required=required)
    return value


def _mask_configured_secret(value: str) -> str:
    if not value:
        return "未配置"
    if len(value) <= 8:
        return "已配置"
    return f"已配置（{value[:4]}...{value[-4:]}）"


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
    _set_nested(config, ["version_check", "enabled"], True)
    _set_nested(config, ["version_check", "branch_name"], os.getenv("NEXTARC_REPO_BRANCH", "feat/one_click_deploy"))
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


def _print_terminal_qr(url: str) -> bool:
    """在终端渲染二维码，失败时返回 False 以便保留链接兜底。"""

    try:
        import qrcode
    except ImportError:
        return False

    try:
        qr = qrcode.QRCode(border=2)
        qr.add_data(url)
        qr.make(fit=True)
        matrix = qr.get_matrix()
    except Exception:
        return False

    print("请使用飞书扫描下方二维码完成应用创建：")
    for row in matrix:
        print("".join("\033[40m  \033[0m" if cell else "\033[47m  \033[0m" for cell in row))
    return True


def _get_registration_poll_interval(server_interval: float) -> float:
    raw_interval = os.getenv("NEXTARC_FEISHU_REGISTRATION_POLL_INTERVAL", "")
    if not raw_interval:
        return max(server_interval, DEFAULT_REGISTRATION_POLL_INTERVAL)

    try:
        configured_interval = float(raw_interval)
    except ValueError:
        print(
            f"警告：NEXTARC_FEISHU_REGISTRATION_POLL_INTERVAL={raw_interval!r} 无效，使用默认轮询间隔",
            file=sys.stderr,
        )
        configured_interval = DEFAULT_REGISTRATION_POLL_INTERVAL

    return max(server_interval, configured_interval, 1.0)


def _post_registration(base_url: str, data: dict[str, str]) -> dict[str, Any]:
    encoded = urlencode(data).encode("utf-8")
    request = Request(
        base_url + REGISTRATION_ENDPOINT,
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")

    try:
        result = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"飞书应用创建接口返回了无法解析的响应: {payload[:200]}") from exc

    if not isinstance(result, dict):
        raise RuntimeError(f"飞书应用创建接口返回了异常响应: {payload[:200]}")
    return result


def _build_registration_qr_url(uri: str) -> str:
    parsed = urlparse(uri)
    params = parse_qs(parsed.query)
    params["from"] = "sdk"
    params["tp"] = "sdk"
    params["source"] = REGISTRATION_SOURCE
    return urlunparse(parsed._replace(query=urlencode(params, doseq=True)))


def _register_feishu() -> tuple[str, str, str]:
    try:
        import lark_oapi as lark
    except ImportError as exc:
        raise RuntimeError("未安装 lark-oapi，请先安装依赖") from exc

    del lark

    def on_qr_code(info: dict[str, Any]) -> None:
        url = info["url"]
        print()
        rendered = _print_terminal_qr(url)
        if rendered:
            print()
            print("如果二维码无法扫描，也可以在浏览器打开以下链接：")
        else:
            print("请在浏览器打开以下链接完成应用创建：")
        print(url)
        print(f"链接有效期约 {info.get('expire_in', 600)} 秒")
        print()

    def on_status_change(info: dict[str, Any]) -> None:
        status = info.get("status")
        if status == "polling":
            interval = info.get("interval")
            if interval:
                print(f"等待飞书授权确认... 当前轮询间隔 {interval:g} 秒")
            else:
                print("等待飞书授权确认...")
        elif status == "slow_down":
            print(f"飞书要求降低轮询频率，当前间隔 {info.get('interval')} 秒")
        elif status == "domain_switched":
            print("已切换到 Lark 国际版认证域")

    result = _run_feishu_registration(
        on_qr_code=on_qr_code,
        on_status_change=on_status_change,
    )
    app_id = result["client_id"]
    app_secret = result["client_secret"]
    open_id = (result.get("user_info") or {}).get("open_id", "")
    return app_id, app_secret, open_id


def _run_feishu_registration(on_qr_code, on_status_change) -> dict[str, Any]:
    base_url = FEISHU_REGISTRATION_DOMAIN

    init_res = _post_registration(base_url, {"action": "init"})
    methods = init_res.get("supported_auth_methods") or []
    if "client_secret" not in methods:
        raise RuntimeError("飞书应用创建接口不支持 client_secret 授权方式")

    begin_res = _post_registration(
        base_url,
        {
            "action": "begin",
            "archetype": "PersonalAgent",
            "auth_method": "client_secret",
            "request_user_info": "open_id",
        },
    )

    device_code = begin_res.get("device_code")
    verification_uri = begin_res.get("verification_uri_complete")
    if not device_code or not verification_uri:
        error = begin_res.get("error", "")
        error_desc = begin_res.get("error_description", "")
        detail = f"{error} {error_desc}".strip() or str(begin_res)[:200]
        raise RuntimeError(f"飞书应用创建初始化失败: {detail}")

    server_interval = float(begin_res.get("interval", 5))
    interval = _get_registration_poll_interval(server_interval)
    expire_in = int(begin_res.get("expires_in", 600))

    qr_url = _build_registration_qr_url(verification_uri)
    on_qr_code({"url": qr_url, "expire_in": expire_in})
    on_status_change({"status": "polling", "interval": interval})

    deadline = time.monotonic() + expire_in
    domain_switched = False

    while time.monotonic() < deadline:
        time.sleep(interval)

        poll_res = _post_registration(base_url, {"action": "poll", "device_code": device_code})

        if poll_res.get("client_id") and poll_res.get("client_secret"):
            result = {
                "client_id": poll_res["client_id"],
                "client_secret": poll_res["client_secret"],
            }
            if poll_res.get("user_info"):
                result["user_info"] = poll_res["user_info"]
            return result

        user_info = poll_res.get("user_info") or {}
        if user_info.get("tenant_brand") == "lark" and not domain_switched:
            base_url = LARK_REGISTRATION_DOMAIN
            domain_switched = True
            on_status_change({"status": "domain_switched"})
            continue

        error = poll_res.get("error", "")
        error_desc = poll_res.get("error_description", "")

        if error == "authorization_pending":
            on_status_change({"status": "polling", "interval": interval})
            continue

        if error == "slow_down":
            interval += 5
            on_status_change({"status": "slow_down", "interval": interval})
            continue

        if error == "access_denied":
            raise RuntimeError("飞书应用创建授权被拒绝")

        if error == "expired_token":
            raise RuntimeError("飞书应用创建二维码已过期")

        raise RuntimeError(f"飞书应用创建失败: {error or 'unknown'} {error_desc}".strip())

    raise RuntimeError("飞书应用创建超时，二维码已过期")


def cmd_bootstrap(args: argparse.Namespace) -> int:
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_STATE_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)

    print("NextArc 初始化")
    username = input("请输入 USTC 学号: ").strip()
    password = getpass.getpass("请输入 USTC 统一身份认证密码: ").strip()
    if not username or not password:
        print("USTC 学号和密码不能为空", file=sys.stderr)
        return 1

    app_id = app_secret = open_id = ""
    if args.skip_feishu_register:
        print("已跳过飞书应用创建。之后可运行 nextarc feishu-register，或通过安装脚本 --migrate 迁移旧凭据。")
    else:
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


async def _test_ai_config(config: dict[str, Any], api_key: str) -> tuple[bool, str]:
    from src.config.settings import load_prompt_file_strict
    from src.core.ai_filter import AIFilter

    system_prompt_file = _get_nested(config, ["ai", "system_prompt_file"], "config/prompts/system_prompt.md")
    user_prompt_file = _get_nested(config, ["ai", "user_prompt_file"], "config/prompts/user_prompt.md")
    system_prompt = load_prompt_file_strict(system_prompt_file)
    user_prompt = load_prompt_file_strict(user_prompt_file)

    ai_filter = AIFilter(
        api_key=api_key,
        base_url=_get_nested(config, ["ai", "base_url"], "") or None,
        model=_get_nested(config, ["ai", "model"], ""),
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=_get_nested(config, ["ai", "temperature"], None),
        timeout=int(_get_nested(config, ["ai", "timeout"], 30)),
        extra_body=_get_nested(config, ["ai", "extra_body"], None),
    )
    return await ai_filter.test_connection()


def cmd_ai_config(_args: argparse.Namespace) -> int:
    config = _load_yaml(DEFAULT_CONFIG_PATH)
    if not config:
        config = _prepare_base_config()

    print("NextArc AI 筛选配置")
    env_values = _read_env_file(DEFAULT_ENV_PATH)
    enabled = _prompt_bool("是否启用 AI 筛选？", bool(_get_nested(config, ["ai", "enabled"], False)))
    if not enabled:
        _set_nested(config, ["ai", "enabled"], False)
        _set_nested(config, ["ai", "api_key"], "")
        _set_nested(config, ["monitor", "use_ai_filter"], False)
        env_values.pop("NEXTARC_AI_API_KEY", None)
        _write_yaml(DEFAULT_CONFIG_PATH, config)
        _write_env_file(DEFAULT_ENV_PATH, env_values)
        _chown_config_for_nextarc([DEFAULT_CONFIG_DIR, DEFAULT_CONFIG_PATH, DEFAULT_ENV_PATH])
        print("AI 筛选已禁用。请重启 nextarc 服务使配置生效。")
        return 0

    current_api_key = env_values.get("NEXTARC_AI_API_KEY") or _get_nested(config, ["ai", "api_key"], "")
    while True:
        print()
        base_url = _prompt_text("请输入 API Base URL（可留空使用 OpenAI 默认）", _get_nested(config, ["ai", "base_url"], ""))
        print(f"当前 API Key: {_mask_configured_secret(current_api_key)}")
        api_key = input("请输入 AI API Key（输入内容会显示；直接回车保留当前值）: ").strip() or current_api_key
        model = _prompt_text("请输入模型名称", _get_nested(config, ["ai", "model"], ""), required=True)
        temperature = _prompt_float(
            "请输入 temperature",
            _get_nested(config, ["ai", "temperature"], None),
            default=0.3,
            minimum=0.0,
            maximum=2.0,
        )
        user_info = _prompt_multiline(
            "请描述你的活动偏好",
            _get_nested(config, ["ai", "user_info"], ""),
            required=True,
        )

        if not api_key:
            print("API Key 不能为空")
            continue

        _set_nested(config, ["ai", "enabled"], False)
        _set_nested(config, ["monitor", "use_ai_filter"], False)
        _set_nested(config, ["ai", "base_url"], base_url)
        _set_nested(config, ["ai", "model"], model)
        _set_nested(config, ["ai", "temperature"], temperature)
        _set_nested(config, ["ai", "user_info"], user_info)
        current_api_key = api_key

        print("正在测试 AI API 配置...")
        try:
            ok, detail = asyncio.run(_test_ai_config(config, api_key))
        except Exception as exc:
            ok, detail = False, str(exc)

        if ok:
            print(detail)
            _set_nested(config, ["ai", "enabled"], True)
            _set_nested(config, ["ai", "api_key"], "")
            _set_nested(config, ["monitor", "use_ai_filter"], True)
            env_values["NEXTARC_AI_API_KEY"] = api_key
            break

        print(f"AI API 配置测试失败: {detail}", file=sys.stderr)
        action = input("按回车保留当前内容并重新修改；输入 q 放弃配置 AI 筛选: ").strip().lower()
        if action == "q":
            _set_nested(config, ["ai", "enabled"], False)
            _set_nested(config, ["ai", "api_key"], "")
            _set_nested(config, ["monitor", "use_ai_filter"], False)
            env_values.pop("NEXTARC_AI_API_KEY", None)
            print("已放弃配置 AI 筛选，AI 筛选保持关闭。")
            break

    _write_yaml(DEFAULT_CONFIG_PATH, config)
    _write_env_file(DEFAULT_ENV_PATH, env_values)
    _chown_config_for_nextarc([DEFAULT_CONFIG_DIR, DEFAULT_CONFIG_PATH, DEFAULT_ENV_PATH])
    print("AI 配置已更新。请重启 nextarc 服务使配置生效。")
    return 0


def _parse_time_ranges(raw: str) -> list[dict[str, str]]:
    if not raw.strip():
        return []

    ranges: list[dict[str, str]] = []
    for item in raw.replace("，", ",").split(","):
        item = item.strip()
        if not item:
            continue
        if "-" not in item:
            raise ValueError(f"时间段缺少 - 分隔符: {item}")
        start, end = [part.strip() for part in item.split("-", 1)]
        try:
            start_time = datetime.strptime(start, "%H:%M")
            end_time = datetime.strptime(end, "%H:%M")
        except ValueError as exc:
            raise ValueError(f"时间格式错误: {item}，应为 HH:MM-HH:MM，如 14:00-16:00") from exc
        if start_time >= end_time:
            raise ValueError(f"时间段无效: {item}，开始时间必须早于结束时间")
        ranges.append({"start": start, "end": end})
    return ranges


def cmd_preference_config(_args: argparse.Namespace) -> int:
    from pydantic import ValidationError
    from src.config.preferences import PushPreferences

    preferences = _load_yaml(DEFAULT_PREFERENCES_PATH)
    if not preferences:
        preferences = _load_preferences_template()

    print("NextArc 推送偏好配置")
    time_filter = preferences.setdefault("time_filter", {})
    enabled = _prompt_bool("是否启用空闲时间筛选？", bool(time_filter.get("enabled", False)))
    time_filter["enabled"] = enabled

    print("时间重叠判断模式：partial=有重叠即过滤，full=完全包含才过滤，threshold=按重叠比例过滤")
    current_mode = str(time_filter.get("overlap_mode") or "partial")
    while True:
        overlap_mode = _prompt_text("请选择模式 partial/full/threshold", current_mode, required=True)
        if overlap_mode in {"partial", "full", "threshold"}:
            time_filter["overlap_mode"] = overlap_mode
            break
        print("模式只能是 partial、full 或 threshold")

    threshold = _prompt_float(
        "请输入 threshold 模式的重叠比例阈值",
        time_filter.get("overlap_threshold"),
        default=0.3,
        minimum=0.0,
        maximum=1.0,
    )
    time_filter["overlap_threshold"] = threshold

    weekly = time_filter.setdefault("weekly_preferences", {})
    days = [
        ("monday", "周一"),
        ("tuesday", "周二"),
        ("wednesday", "周三"),
        ("thursday", "周四"),
        ("friday", "周五"),
        ("saturday", "周六"),
        ("sunday", "周日"),
    ]

    print("按天填写没空时间段。格式示例：08:00-10:00, 14:00-16:30；直接回车保留，输入 - 清空。")
    for key, label in days:
        current_ranges = weekly.get(key) or []
        current = ", ".join(f"{item.get('start')}-{item.get('end')}" for item in current_ranges if isinstance(item, dict))
        while True:
            raw = input(f"{label}没空时间段 [{current or '无'}]: ").strip()
            if not raw:
                break
            if raw == "-":
                weekly[key] = []
                break
            try:
                weekly[key] = _parse_time_ranges(raw)
                break
            except ValueError as exc:
                print(exc)

    try:
        validated = PushPreferences(**preferences)
    except ValidationError as exc:
        print("偏好配置校验失败：", file=sys.stderr)
        print(exc, file=sys.stderr)
        return 1

    _write_yaml(DEFAULT_PREFERENCES_PATH, validated.model_dump())
    _chown_config_for_nextarc([DEFAULT_CONFIG_DIR, DEFAULT_PREFERENCES_PATH])
    print(f"偏好配置已更新: {DEFAULT_PREFERENCES_PATH}")
    print("请重启 nextarc 服务使配置生效。")
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
        version = getattr(lark, "__version__", "unknown")
        print(f"[OK] lark-oapi: 已安装 version={version}")
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
    parser.add_argument("--preference-config", action="store_true", help="交互式配置推送偏好")
    parser.add_argument("--feishu-register", action="store_true", help="重新注册飞书应用")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("run", help="启动 NextArc 服务")
    bootstrap_parser = subparsers.add_parser("bootstrap", help="初始化配置和飞书应用")
    bootstrap_parser.add_argument(
        "--skip-feishu-register",
        action="store_true",
        help="跳过飞书应用创建，稍后通过 feishu-register 或安装脚本 --migrate 补充凭据",
    )
    subparsers.add_parser("feishu-register", help="重新注册飞书应用")
    subparsers.add_parser("ai-config", help="交互式配置 AI 筛选")
    subparsers.add_parser("preference-config", help="交互式配置推送偏好")
    subparsers.add_parser("doctor", help="检查部署状态")
    return parser


def main_cli() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.ai_config:
            return cmd_ai_config(args)
        if args.preference_config:
            return cmd_preference_config(args)
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
            case "preference-config":
                return cmd_preference_config(args)
            case "doctor":
                return cmd_doctor(args)
            case _:
                parser.print_help()
                return 1
    except RuntimeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main_cli())
