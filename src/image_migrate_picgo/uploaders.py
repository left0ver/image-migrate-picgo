import json
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def default_picgo_config() -> Path:
    return Path.home() / ".picgo" / "config.json"


def _picgo_command(command: str | Path | None) -> str:
    candidate = "picgo" if command is None else str(Path(command).expanduser())
    executable = shutil.which(candidate)
    if executable is None:
        raise FileNotFoundError(
            f"没有找到 PicGo CLI：{candidate}。请安装 PicGo CLI 或使用 --picgo-command 指定路径"
        )
    return str(Path(executable).resolve(strict=True))


def configure_picgo_cli(
    command: str | Path | None = None,
    config: str | Path | None = None,
) -> Path:
    picgo = _picgo_command(command)
    config_path = (
        default_picgo_config() if config is None else Path(config).expanduser()
    )
    config_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [picgo, "--config", str(config_path), "set", "uploader"],
        check=True,
    )
    return config_path


class Uploader(Protocol):
    def upload(self, sources: Sequence[str | Path]) -> Sequence[str]: ...


def _validate_urls(values: object, expected: int) -> list[str]:
    if not isinstance(values, list) or len(values) != expected:
        raise RuntimeError("PicGo 返回的 URL 数量与图片数量不一致")
    if not all(
        isinstance(value, str) and urlsplit(value).scheme in {"http", "https"}
        for value in values
    ):
        raise RuntimeError("PicGo 返回了无效的图片 URL")
    return values


class ServerUploader:
    def __init__(
        self,
        url: str = "http://127.0.0.1:36677/upload",
        *,
        secret: str | None = None,
        timeout: float = 60,
    ) -> None:
        self.url = url
        self.secret = secret
        self.timeout = timeout

    def upload(self, sources: Sequence[str | Path]) -> list[str]:
        body = json.dumps({"list": [str(source) for source in sources]}).encode()
        headers = {"Content-Type": "application/json"}
        if self.secret:
            headers["Authorization"] = f"Bearer {self.secret}"
        request = Request(self.url, data=body, headers=headers, method="POST")
        with urlopen(request, timeout=self.timeout) as response:
            result = json.loads(response.read())
        if result.get("success") is not True:
            raise RuntimeError(result.get("message", "PicGo Server 上传失败"))
        return _validate_urls(result.get("result"), len(sources))


class CliUploader:
    def __init__(
        self,
        command: str | Path | None = None,
        *,
        config: str | Path | None = None,
    ) -> None:
        self.command = _picgo_command(command)
        config_path = (
            default_picgo_config() if config is None else Path(config).expanduser()
        )
        if not config_path.is_file():
            print(f"没有找到 PicGo 配置文件，将启动配置向导：{config_path}")
            configure_picgo_cli(self.command, config_path)
            if not config_path.is_file():
                raise FileNotFoundError(f"PicGo 配置文件尚未创建：{config_path}")
        self.config = str(config_path)

    def upload(self, sources: Sequence[str | Path]) -> list[str]:
        command = [self.command, "--config", self.config]
        command.extend(("upload", *(str(source) for source in sources)))
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
        lines = (result.stdout + "\n" + result.stderr).splitlines()
        urls = [
            line.strip()
            for line in lines
            if urlsplit(line.strip()).scheme in {"http", "https"}
        ]
        if not urls:
            output = "\n".join(line for line in lines if line.strip())
            raise RuntimeError(output or "PicGo CLI 没有返回图片 URL")
        return _validate_urls(urls, len(sources))
