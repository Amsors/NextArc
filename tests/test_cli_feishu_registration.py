"""飞书应用注册命令回归测试。"""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from unittest.mock import patch

from src import cli


class FeishuRegistrationHttpTest(unittest.TestCase):
    def test_post_registration_reads_http_error_json_body(self) -> None:
        body = json.dumps(
            {
                "error": "authorization_pending",
                "error_description": "wait for user approval",
            }
        ).encode("utf-8")
        error = HTTPError(
            url="https://accounts.feishu.cn/oauth/v1/app/registration",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=io.BytesIO(body),
        )

        with patch.object(cli, "urlopen", side_effect=error):
            result = cli._post_registration("https://accounts.feishu.cn", {"action": "poll"})

        self.assertEqual(result["error"], "authorization_pending")

    def test_post_registration_rejects_non_object_response(self) -> None:
        with patch.object(cli, "urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = b"[]"

            with self.assertRaisesRegex(RuntimeError, "异常响应"):
                cli._post_registration("https://accounts.feishu.cn", {"action": "init"})

    def test_run_registration_reports_begin_error_without_key_error(self) -> None:
        responses = [
            {"supported_auth_methods": ["client_secret"]},
            {"error": "invalid_request", "error_description": "bad archetype"},
        ]

        with patch.object(cli, "_post_registration", side_effect=responses):
            with self.assertRaisesRegex(RuntimeError, "初始化失败: invalid_request bad archetype"):
                cli._run_feishu_registration(lambda _info: None, lambda _info: None)


class CliErrorHandlingTest(unittest.TestCase):
    def test_main_cli_prints_runtime_error_without_traceback(self) -> None:
        stderr = io.StringIO()
        with patch.object(sys, "argv", ["nextarc", "feishu-register"]):
            with patch.object(cli, "cmd_feishu_register", side_effect=RuntimeError("飞书应用创建失败")):
                with patch("sys.stderr", stderr):
                    exit_code = cli.main_cli()

        self.assertEqual(exit_code, 1)
        self.assertEqual(stderr.getvalue().strip(), "错误：飞书应用创建失败")


class BootstrapTest(unittest.TestCase):
    def test_bootstrap_can_skip_feishu_registration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "config"
            state_dir = root / "state"
            log_dir = root / "log"

            patches = [
                patch.object(cli, "DEFAULT_CONFIG_DIR", config_dir),
                patch.object(cli, "DEFAULT_STATE_DIR", state_dir),
                patch.object(cli, "DEFAULT_LOG_DIR", log_dir),
                patch.object(cli, "DEFAULT_CONFIG_PATH", config_dir / "config.yaml"),
                patch.object(cli, "DEFAULT_PREFERENCES_PATH", config_dir / "preferences.yaml"),
                patch.object(cli, "DEFAULT_ENV_PATH", config_dir / "nextarc.env"),
                patch.object(cli, "DEFAULT_STATE_PATH", state_dir / "state.yaml"),
                patch("builtins.input", return_value="PB00000000"),
                patch.object(cli.getpass, "getpass", return_value="password"),
                patch.object(cli, "_register_feishu", side_effect=AssertionError("should not register")),
            ]
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9]:
                exit_code = cli.cmd_bootstrap(SimpleNamespace(skip_feishu_register=True))

            self.assertEqual(exit_code, 0)
            env_values = cli._read_env_file(config_dir / "nextarc.env")
            self.assertEqual(env_values["USTC_USERNAME"], "PB00000000")
            self.assertEqual(env_values["USTC_PASSWORD"], "password")
            self.assertEqual(env_values["NEXTARC_FEISHU_APP_ID"], "")
            self.assertEqual(env_values["NEXTARC_FEISHU_APP_SECRET"], "")


if __name__ == "__main__":
    unittest.main()
