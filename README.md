# image-migrate-picgo

通过 PicGo 迁移单个 Markdown 文件中的图片。支持本地图片、HTTP 图片、HTTPS 图片、Data URL、引用式 Markdown 图片和 HTML `<img>`，并保留普通链接与代码区域中的文本。

## 安装

```bash
pip install image-migrate-picgo
```

使用 PicGo.app 时，请在设置中启动 PicGo Server；默认上传地址为 `http://127.0.0.1:36677/upload`。

## 支持的图片写法

Markdown 图片、引用式图片、HTML `<img>` 和 Data URL 都会进入迁移流程：

```markdown
![local](./images/photo.png)
![remote](https://example.com/photo.png)
![reference][photo]

[photo]: ./images/photo.png

<img src="./images/photo.png" alt="Photo" width="600">

![inline](data:image/png;base64,...)
```

HTML 图片迁移后会保留 `alt`、`title`、`width` 等属性。Data URL 会解码成临时图片文件，然后交给 PicGo 上传。行内代码和代码块中的图片文本保持原有内容。

公网图片 URL 会直接交给 PicGo 上传；本地图片与 Data URL 仍通过本地文件上传。

## CLI

CLI 使用 [Typer](https://github.com/fastapi/typer) 构建。

通过 PicGo Server 更新原文件：

```bash
image-migrate-picgo README.md
```

写入另一个文件：

```bash
image-migrate-picgo README.md --output README.migrated.md
```

通过 PicGo CLI 上传：

```bash
image-migrate-picgo README.md --method cli
```

CLI 上传调用用户安装的 PicGo CLI，默认从 `PATH` 查找 `picgo`。默认读取配置文件 `~/.picgo/config.json`；配置文件缺失时会自动启动 uploader 配置向导。安装 PicGo CLI 的方式由用户选择，本工具不会自动下载。

也可以随时主动启动配置向导：

```bash
image-migrate-picgo --configure
```

指定 PicGo CLI 可执行文件和配置文件：

```bash
image-migrate-picgo README.md \
  --method cli \
  --picgo-command /path/to/picgo \
  --picgo-config /path/to/config.json
```

## Python API

```python
from image_migrate_picgo import ServerUploader, migrate_markdown

result = migrate_markdown("README.md", ServerUploader())
print(result.output_path, result.urls)
```

PicGo CLI 的调用方式：

```python
from image_migrate_picgo import CliUploader, migrate_markdown

result = migrate_markdown("README.md", CliUploader())
```

`CliUploader()` 从 `PATH` 查找 PicGo CLI，并使用默认配置路径。可以通过 `command` 和 `config` 传入自定义路径。

`migrate_markdown()` 每次处理一个文件。目录迁移可以遍历 Markdown 文件并多次调用该函数。

## 开发检查

```bash
uv run python -m unittest discover -s test
uv build
```

`test/smoke_remote.md` 提供两张公网图片，可用于带有可用 PicGo 配置的完整冒烟测试：

```bash
image-migrate-picgo test/smoke_remote.md --output test/smoke_output.md
```

`test/fixtures/markdown/` 包含 10 个测试文件，`test/fixtures/images/` 包含 4 张本地 SVG。单元测试会检查每个文件的图片解析结果与本地路径。启动 PicGo Server 后，可以逐个进行完整上传测试：

```bash
mkdir -p test/fixtures/output
for markdown in test/fixtures/markdown/*.md test/fixtures/markdown/nested/*.md; do
  uv run image-migrate-picgo "$markdown" --output "test/fixtures/output/${markdown##*/}"
done
```

测试结果保存在 `test/fixtures/output/`，该目录不会进入 Git。
