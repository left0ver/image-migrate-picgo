import unittest
from pathlib import Path

from typer.testing import CliRunner

from image_migrate_picgo.cli import app
from image_migrate_picgo.uploaders import _picgo_command, default_picgo_config


class CliTest(unittest.TestCase):
    def test_help_shows_user_picgo_options(self) -> None:
        result = CliRunner().invoke(app, ["--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn(str(default_picgo_config()), result.stdout)
        self.assertIn("--picgo-command", result.stdout)
        self.assertIn("--picgo-config", result.stdout)
        self.assertIn("--configure", result.stdout)
        self.assertNotIn("下载 PicGo", result.stdout)

    def test_missing_picgo_command_fails(self) -> None:
        with self.assertRaises(FileNotFoundError):
            _picgo_command(Path("test/fixtures/no-picgo-command"))


if __name__ == "__main__":
    unittest.main()
