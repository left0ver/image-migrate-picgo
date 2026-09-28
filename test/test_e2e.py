"""使用本机 PicGo 真实上传图片的端到端测试。

默认跳过。通过环境变量 PICGO_E2E 开启：

    PICGO_E2E=all uv run python -m unittest discover -s test -p test_e2e.py -v

PICGO_E2E 取值为 server、cli 或逗号分隔的组合，all 表示两者都测。
可选环境变量：
    PICGO_E2E_SERVER_URL     PicGo Server 上传地址，默认 http://127.0.0.1:36677/upload
    PICGO_E2E_SERVER_SECRET  PicGo Server 访问密钥
    PICGO_E2E_COMMAND        PicGo CLI 可执行文件，默认从 PATH 查找 picgo
    PICGO_E2E_CONFIG         PicGo CLI 配置文件，默认 ~/.picgo/config.json

注意：测试会把 fixtures 中的图片真实上传到当前配置的图床。
"""

import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from image_migrate_picgo import image_sources, rewrite_markdown
from image_migrate_picgo.uploaders import default_picgo_config

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"
SUMMARY_RE = re.compile(r"已迁移 (\d+) 处图片，上传 (\d+) 个文件")
DEFAULT_SERVER_URL = "http://127.0.0.1:36677/upload"


def _enabled_methods() -> set[str]:
    value = os.environ.get("PICGO_E2E", "").strip().lower()
    if value in {"1", "true", "all"}:
        return {"server", "cli"}
    return {method.strip() for method in value.split(",") if method.strip()}


def _is_remote(source: str) -> bool:
    return urlsplit(source).scheme in {"http", "https"}


class _PicGoE2E:
    """两种上传方式共用的测试，子类提供命令行参数并检查 PicGo 是否可用。"""

    upload_args: list[str]

    def setUp(self) -> None:
        self._directory = TemporaryDirectory(prefix="image-migrate-picgo-e2e-")
        self.workspace = Path(self._directory.name)
        shutil.copytree(FIXTURE_DIRECTORY, self.workspace / "fixtures")
        self.markdown_directory = self.workspace / "fixtures" / "markdown"
        self.checked_urls: set[str] = set()

    def tearDown(self) -> None:
        self._directory.cleanup()

    def run_cli(
        self, *args: str | Path, returncode: int = 0
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "image_migrate_picgo.cli",
                *map(str, args),
                *self.upload_args,
            ],
            check=False,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=300,
        )
        if result.returncode != returncode:
            self.fail(
                f"imp 退出码 {result.returncode}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    def assert_migrated(self, original: str, migrated: str, stdout: str) -> None:
        before = image_sources(original)
        after = image_sources(migrated)
        self.assertEqual(len(after), len(before))

        # 同一来源只上传一次，所有引用都应替换为同一个 URL
        replacements: dict[str, str] = {}
        for source, url in zip(before, after, strict=True):
            self.assertTrue(_is_remote(url), f"{source} 没有被替换为图床 URL：{url}")
            self.assertEqual(replacements.setdefault(source, url), url)
        self.assertEqual(len(set(replacements.values())), len(replacements))

        # 除图片地址外，文档其余部分保持不变
        self.assertEqual(rewrite_markdown(original, replacements), migrated)

        summary = SUMMARY_RE.search(stdout)
        self.assertTrue(summary, f"没有找到迁移结果输出：{stdout}")
        self.assertEqual(
            (int(summary[1]), int(summary[2])), (len(before), len(replacements))
        )

        for url in replacements.values():
            self.assert_url_serves_image(url)

    def assert_url_serves_image(self, url: str) -> None:
        if url in self.checked_urls:
            return
        request = Request(url, headers={"User-Agent": "image-migrate-picgo-e2e"})
        with urlopen(request, timeout=60) as response:
            self.assertEqual(response.status, 200, url)
            self.assertTrue(response.read(), f"图床返回了空内容：{url}")
        self.checked_urls.add(url)

    def assert_no_temporary_directory(self) -> None:
        leftovers = list(self.workspace.rglob(".image-migrate-picgo-*"))
        self.assertEqual(leftovers, [])

    def test_migrates_fixture_documents(self) -> None:
        documents = sorted(self.markdown_directory.rglob("*.md"))
        self.assertTrue(documents)
        for document in documents:
            with self.subTest(document=document.name):
                original = document.read_text(encoding="utf-8")
                output = self.workspace / f"output-{document.name}"
                result = self.run_cli(document, "--output", output)

                self.assertEqual(document.read_text(encoding="utf-8"), original)
                self.assert_migrated(
                    original, output.read_text(encoding="utf-8"), result.stdout
                )
        self.assert_no_temporary_directory()

    def test_updates_markdown_in_place(self) -> None:
        document = self.markdown_directory / "10-data-url.md"
        original = document.read_text(encoding="utf-8")

        result = self.run_cli(document)

        self.assert_migrated(
            original, document.read_text(encoding="utf-8"), result.stdout
        )
        self.assert_no_temporary_directory()

    def test_migrates_directory_and_reports_failed_files(self) -> None:
        # 只保留部分 fixture，减少真实上传的图片数量
        for document in self.markdown_directory.rglob("*.md"):
            if document.name not in {"01-inline.md", "06-nested.md", "10-data-url.md"}:
                document.unlink()
        originals = {
            document: document.read_text(encoding="utf-8")
            for document in sorted(self.markdown_directory.rglob("*.md"))
        }
        broken = {
            self.markdown_directory
            / "missing-local.md": "![丢失](../images/missing.svg)\n",
            self.markdown_directory / "missing-remote.md": (
                "![失效](https://www.python.org/static/community_logos/"
                "image-migrate-picgo-missing.png)\n"
            ),
            self.markdown_directory / ".drafts" / "draft.md": (
                "![草稿](../../images/sun.svg)\n"
            ),
        }
        for document, content in broken.items():
            document.parent.mkdir(exist_ok=True)
            document.write_text(content, encoding="utf-8")

        result = self.run_cli(self.markdown_directory, returncode=1)

        lines = result.stdout.splitlines()
        for document, original in originals.items():
            with self.subTest(document=document.name):
                summary = next(
                    (line for line in lines if line.endswith(str(document.resolve()))),
                    "",
                )
                self.assert_migrated(
                    original, document.read_text(encoding="utf-8"), summary
                )
        # 失败的文件和隐藏目录中的文件保持不变
        for document, content in broken.items():
            self.assertEqual(document.read_text(encoding="utf-8"), content)
        for name in ("missing-local.md", "missing-remote.md"):
            document = (self.markdown_directory / name).resolve()
            self.assertIn(f"迁移失败：{document}", result.stderr)
        self.assertIn("missing.svg", result.stderr)
        self.assertIn("HTTP Error 404", result.stderr)
        self.assertIn("迁移完成：成功 3 个，失败 2 个", result.stdout)
        self.assert_no_temporary_directory()


def _server_heartbeat(upload_url: str, secret: str | None) -> str | None:
    """返回 PicGo Server 不可用的原因，可用时返回 None。"""
    parts = urlsplit(upload_url)
    heartbeat = urlunsplit((parts.scheme, parts.netloc, "/heartbeat", "", ""))
    headers = {"Authorization": f"Bearer {secret}"} if secret else {}
    try:
        with urlopen(
            Request(heartbeat, headers=headers, method="POST"), timeout=5
        ) as response:
            result = json.loads(response.read())
    except OSError as error:
        return f"无法连接 PicGo Server（{heartbeat}）：{error}"
    if result.get("success") is not True:
        return f"PicGo Server 心跳检测失败：{result}"
    return None


@unittest.skipUnless("server" in _enabled_methods(), "设置 PICGO_E2E=server 开启")
class ServerE2ETest(_PicGoE2E, unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        url = os.environ.get("PICGO_E2E_SERVER_URL", DEFAULT_SERVER_URL)
        secret = os.environ.get("PICGO_E2E_SERVER_SECRET") or None
        if error := _server_heartbeat(url, secret):
            raise RuntimeError(f"{error}。请打开 PicGo 桌面应用并开启 PicGo Server")
        cls.upload_args = ["--method", "server", "--server-url", url]
        if secret:
            cls.upload_args += ["--server-secret", secret]


@unittest.skipUnless("cli" in _enabled_methods(), "设置 PICGO_E2E=cli 开启")
class CliE2ETest(_PicGoE2E, unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        command = os.environ.get("PICGO_E2E_COMMAND", "picgo")
        executable = shutil.which(str(Path(command).expanduser()))
        if executable is None:
            raise RuntimeError(f"没有找到 PicGo CLI：{command}")
        config = Path(
            os.environ.get("PICGO_E2E_CONFIG", default_picgo_config())
        ).expanduser()
        # 配置文件缺失时 CLI 会启动交互式向导，测试中需要提前拦截
        if not config.is_file():
            raise RuntimeError(
                f"没有找到 PicGo 配置文件：{config}。请先运行 imp --configure"
            )
        pic_bed = json.loads(config.read_text(encoding="utf-8")).get("picBed", {})
        uploader = pic_bed.get("uploader") or pic_bed.get("current")
        if not uploader or not pic_bed.get(uploader):
            raise RuntimeError(
                f"PicGo 配置文件 {config} 中没有 uploader {uploader!r} 的配置。"
                "请先运行 imp --configure"
            )
        cls.upload_args = [
            "--method",
            "cli",
            "--picgo-command",
            executable,
            "--picgo-config",
            str(config),
        ]


if __name__ == "__main__":
    unittest.main()
