import re
import unittest
from pathlib import Path

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

    def test_missing_picgo_command_fails(self) -> None:
        with self.assertRaises(FileNotFoundError):
            _picgo_command(Path("test/fixtures/no-picgo-command"))


if __name__ == "__main__":
    unittest.main()
