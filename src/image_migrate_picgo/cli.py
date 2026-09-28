import os
import platform
import sys
from enum import Enum
from importlib.metadata import version as package_version
from pathlib import Path
from subprocess import SubprocessError
from typing import Annotated

import typer

from .core import MigrationResult, migrate_markdown
from .uploaders import (
    CliUploader,
    ServerUploader,
    configure_picgo_cli,
    default_picgo_config,
)

DEFAULT_PICGO_CONFIG = default_picgo_config()
MARKDOWN_SUFFIXES = {".md", ".markdown"}


class UploadMethod(str, Enum):
    server = "server"
    cli = "cli"


app = typer.Typer(
    help="通过 PicGo 迁移单个 Markdown 文件中的图片",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,
)


def _markdown_files(directory: Path, exclude: Path | None = None) -> list[Path]:
    """递归查找目录下的 Markdown 文件，跳过隐藏目录、node_modules 和 exclude 目录。"""
    files: list[Path] = []
    for root, directories, names in os.walk(directory):
        directories[:] = [
            name
            for name in directories
            if not name.startswith(".")
            and name != "node_modules"
            and (exclude is None or Path(root, name).resolve() != exclude)
        ]
        files.extend(
            Path(root, name)
            for name in names
            if Path(name).suffix.lower() in MARKDOWN_SUFFIXES
        )
    return sorted(files)


def _show_version(value: bool) -> None:
    if value:
        typer.echo(
            typer.style("image-migrate-picgo", bold=True)
            + " "
            + typer.style(package_version("image-migrate-picgo"), fg="green", bold=True)
            + " "
            + typer.style(
                f"(Python {platform.python_version()}, "
                f"{sys.platform} {platform.machine()})",
                dim=True,
            )
        )
        raise typer.Exit()


def _count(value: int, **styles) -> str:
    return typer.style(str(value), bold=True, **styles)


def _echo_result(result: MigrationResult) -> None:
    typer.echo(
        typer.style("✓", fg="green", bold=True)
        + f" 已迁移 {_count(result.migrated_images)} 处图片，"
        f"上传 {_count(result.uploaded_images)} 个文件："
        + typer.style(str(result.output_path), fg="cyan")
    )


def _echo_failure(path: Path, error: Exception) -> None:
    typer.echo(
        typer.style("✗ 迁移失败：", fg="red", bold=True)
        + typer.style(str(path.resolve()), fg="cyan")
        + "\n  "
        + typer.style(f"{type(error).__name__}: {error}", fg="red"),
        err=True,
    )


def _echo_summary(total: int, failures: int) -> None:
    failed = _count(failures, fg="red") if failures else _count(failures)
    typer.echo(
        "\n"
        + typer.style("迁移完成：", bold=True)
        + f"成功 {_count(total - failures, fg='green')} 个，失败 {failed} 个"
    )


@app.command(epilog=f"PicGo CLI 默认配置文件：{DEFAULT_PICGO_CONFIG}")
def main(
    markdown: Annotated[
        Path | None, typer.Argument(help="Markdown 文件或目录路径")
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output", "-o", help="输出路径，默认更新原文件；迁移目录时为输出目录"
        ),
    ] = None,
    method: Annotated[
        UploadMethod, typer.Option(help="上传方式")
    ] = UploadMethod.server,
    server_url: Annotated[
        str,
        typer.Option(help="PicGo Server 上传地址"),
    ] = "http://127.0.0.1:36677/upload",
    server_secret: Annotated[
        str | None,
        typer.Option(help="PicGo Server 访问密钥"),
    ] = None,
    picgo_command: Annotated[
        Path | None,
        typer.Option(help="PicGo CLI 可执行文件，默认从 PATH 查找 picgo"),
    ] = None,
    picgo_config: Annotated[
        Path,
        typer.Option(help="PicGo CLI 配置文件"),
    ] = DEFAULT_PICGO_CONFIG,
    rename: Annotated[
        bool,
        typer.Option(help="上传前将图片重命名为时间戳，格式与 PicGo 应用相同"),
    ] = True,
    configure: Annotated[
        bool,
        typer.Option("--configure", help="启动 PicGo uploader 配置向导"),
    ] = False,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=_show_version,
            is_eager=True,
            help="显示版本号并退出",
        ),
    ] = False,
) -> None:
    if configure:
        config = configure_picgo_cli(picgo_command, picgo_config)
        typer.echo(f"PicGo 配置已保存：{config}")
        return
    if markdown is None:
        raise typer.BadParameter(
            "需要提供 Markdown 文件或目录路径", param_hint="markdown"
        )
    files = None
    if markdown.is_dir():
        if output is not None:
            output = output.expanduser().resolve()
            if output.exists() and not output.is_dir():
                raise typer.BadParameter(
                    "迁移目录时 --output 必须是目录", param_hint="--output"
                )
        files = _markdown_files(markdown, exclude=output)
        if not files:
            typer.echo(f"没有找到 Markdown 文件：{markdown}", err=True)
            raise typer.Exit(1)

    uploader = (
        ServerUploader(server_url, secret=server_secret)
        if method is UploadMethod.server
        else CliUploader(picgo_command, config=picgo_config)
    )
    if files is None:
        _echo_result(
            migrate_markdown(markdown, uploader, output_path=output, rename=rename)
        )
        return

    # 逐个文件迁移：某个文件失败时给出提示，继续处理其余文件
    failures = 0
    for path in files:
        # 指定输出目录时，保持文件在原目录中的相对位置
        target = None if output is None else output / path.relative_to(markdown)
        try:
            if target is not None:
                target.parent.mkdir(parents=True, exist_ok=True)
            result = migrate_markdown(path, uploader, output_path=target, rename=rename)
        except (OSError, RuntimeError, ValueError, SubprocessError) as error:
            failures += 1
            _echo_failure(path, error)
            continue
        _echo_result(result)
    _echo_summary(len(files), failures)
    if failures:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
