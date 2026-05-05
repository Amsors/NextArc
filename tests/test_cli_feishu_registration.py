"""飞书应用注册命令回归测试。"""

import io
import json
import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
