import json
import platform
import re
import sys
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import entry_points, version
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

from typer.testing import CliRunner

from image_migrate_picgo.cli import app
from image_migrate_picgo.uploaders import _picgo_command, default_picgo_config

# Typer 在 GitHub Actions 等环境下会强制输出 ANSI 颜色代码，比较前需要去掉
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class CliTest(unittest.TestCase):
    def test_help_shows_user_picgo_options(self) -> None:
        result = CliRunner().invoke(app, ["--help"])
        output = ANSI_RE.sub("", result.stdout)

        self.assertEqual(result.exit_code, 0)
        self.assertIn(str(default_picgo_config()), output)
        self.assertIn("--picgo-command", output)
        self.assertIn("--picgo-config", output)
        self.assertIn("--configure", output)
        self.assertNotIn("下载 PicGo", output)

    def test_version_shows_package_version(self) -> None:
        for option in ("--version", "-V"):
            with self.subTest(option=option):
                result = CliRunner().invoke(app, [option])

                self.assertEqual(result.exit_code, 0)
                self.assertEqual(
                    ANSI_RE.sub("", result.stdout).strip(),
                    f"image-migrate-picgo {version('image-migrate-picgo')} "
                    f"(Python {platform.python_version()}, "
                    f"{sys.platform} {platform.machine()})",
                )

    def test_installs_short_and_long_commands(self) -> None:
        scripts = {
            script.name
            for script in entry_points(group="console_scripts")
            if script.value == "image_migrate_picgo.cli:app"
        }

        self.assertEqual(scripts, {"imp", "image-migrate-picgo"})

    def test_missing_picgo_command_fails(self) -> None:
        with self.assertRaises(FileNotFoundError):
            _picgo_command(Path("test/fixtures/no-picgo-command"))


class _FakePicGoServer(BaseHTTPRequestHandler):
    """模拟 PicGo Server：图片内容包含 fail 时返回上传失败。"""

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        paths = [Path(item) for item in body["list"]]
        if any(b"fail" in path.read_bytes() for path in paths):
            result = {"success": False, "message": "模拟上传失败"}
        else:
            result = {
                "success": True,
                "result": [f"https://cdn.example/{path.name}" for path in paths],
            }
        data = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args) -> None:
        pass


class DirectoryTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = TemporaryDirectory(prefix="image-test-", dir="test")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.write("images/ok.svg", "<svg>ok</svg>")
        self.write("images/fail.svg", "<svg>fail</svg>")
        self.write("a.md", "![A](images/ok.svg)\n")
        self.write("nested/b.markdown", "![B](../images/ok.svg)\n")
        self.write(".hidden/c.md", "![C](../images/ok.svg)\n")
        self.write("notes.txt", "![D](images/ok.svg)\n")

        server = ThreadingHTTPServer(("127.0.0.1", 0), _FakePicGoServer)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        Thread(target=server.serve_forever, daemon=True).start()
        self.server_url = f"http://127.0.0.1:{server.server_port}/upload"

    def write(self, name: str, content: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def invoke(self, *args: str):
        result = CliRunner().invoke(
            app, [str(self.root), "--server-url", self.server_url, *args]
        )
        return result, ANSI_RE.sub("", result.output)

    def assert_migrated(self, name: str) -> None:
        self.assertIn(
            "https://cdn.example/",
            (self.root / name).read_text(encoding="utf-8"),
        )

    def test_migrates_every_markdown_file_in_directory(self) -> None:
        result, output = self.invoke()

        self.assertEqual(result.exit_code, 0, output)
        self.assert_migrated("a.md")
        self.assert_migrated("nested/b.markdown")
        self.assertEqual(
            (self.root / ".hidden/c.md").read_text(encoding="utf-8"),
            "![C](../images/ok.svg)\n",
        )
        self.assertEqual(
            (self.root / "notes.txt").read_text(encoding="utf-8"),
            "![D](images/ok.svg)\n",
        )
        self.assertIn("成功 2 个，失败 0 个", output)

    def test_reports_files_whose_images_fail_to_upload(self) -> None:
        failed = self.write("failed.md", "![F](images/fail.svg)\n")
        missing = self.write("missing.md", "![M](images/missing.svg)\n")

        result, output = self.invoke()

        self.assertEqual(result.exit_code, 1, output)
        self.assert_migrated("a.md")
        self.assert_migrated("nested/b.markdown")
        self.assertEqual(failed.read_text(encoding="utf-8"), "![F](images/fail.svg)\n")
        self.assertEqual(
            missing.read_text(encoding="utf-8"), "![M](images/missing.svg)\n"
        )
        self.assertIn(f"迁移失败：{failed.resolve()}", output)
        self.assertIn("模拟上传失败", output)
        self.assertIn(f"迁移失败：{missing.resolve()}", output)
        self.assertIn("missing.svg", output)
        self.assertIn("成功 2 个，失败 2 个", output)

    def test_writes_directory_to_output_directory(self) -> None:
        result, output = self.invoke("--output", str(self.root / "out"))

        self.assertEqual(result.exit_code, 0, output)
        self.assert_not_migrated()
        self.assert_migrated("out/a.md")
        self.assert_migrated("out/nested/b.markdown")
        self.assertFalse((self.root / "out/.hidden").exists())
        self.assertIn("成功 2 个，失败 0 个", output)

        # 再次迁移时跳过位于源目录内的输出目录
        result, output = self.invoke("--output", str(self.root / "out"))
        self.assertIn("成功 2 个，失败 0 个", output)

    def test_rejects_file_as_output_for_directory(self) -> None:
        self.write("out.md", "")

        result, output = self.invoke("--output", str(self.root / "out.md"))

        self.assertEqual(result.exit_code, 2, output)
        self.assertIn("--output", output)
        self.assert_not_migrated()

    def test_directory_without_markdown_files_fails(self) -> None:
        empty = self.root / "empty"
        empty.mkdir()

        result = CliRunner().invoke(app, [str(empty)])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("没有找到 Markdown 文件", ANSI_RE.sub("", result.output))

    def assert_not_migrated(self) -> None:
        self.assertEqual(
            (self.root / "a.md").read_text(encoding="utf-8"), "![A](images/ok.svg)\n"
        )


if __name__ == "__main__":
    unittest.main()
