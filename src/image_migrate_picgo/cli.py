from enum import Enum
from pathlib import Path
from typing import Annotated

import typer

from .core import migrate_markdown
from .uploaders import (
    CliUploader,
    ServerUploader,
    configure_picgo_cli,
    default_picgo_config,
)

DEFAULT_PICGO_CONFIG = default_picgo_config()


class UploadMethod(str, Enum):
    server = "server"
    cli = "cli"


app = typer.Typer(
    help="通过 PicGo 迁移单个 Markdown 文件中的图片",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,
)


@app.command(epilog=f"PicGo CLI 默认配置文件：{DEFAULT_PICGO_CONFIG}")
def main(
    markdown: Annotated[Path | None, typer.Argument(help="Markdown 文件路径")] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="输出路径，默认更新原文件"),
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
) -> None:
    if configure:
        config = configure_picgo_cli(picgo_command, picgo_config)
        typer.echo(f"PicGo 配置已保存：{config}")
        return
    if markdown is None:
        raise typer.BadParameter("需要提供 Markdown 文件路径", param_hint="markdown")

    uploader = (
        ServerUploader(server_url, secret=server_secret)
        if method is UploadMethod.server
        else CliUploader(picgo_command, config=picgo_config)
    )
    result = migrate_markdown(
        markdown,
        uploader,
        output_path=output,
        rename=rename,
    )
    typer.echo(
        f"已迁移 {result.migrated_images} 处图片，"
        f"上传 {result.uploaded_images} 个文件：{result.output_path}"
    )


if __name__ == "__main__":
    app()
