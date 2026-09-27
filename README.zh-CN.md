<p align="center">
  <img src="assets/logo.svg" alt="image-migrate-picgo logo" width="128">
</p>

<h1 align="center">image-migrate-picgo</h1>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue?style=flat-square" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/PicGo-Server%20%7C%20CLI-blue?style=flat-square" alt="PicGo Server and CLI">
  <img src="https://img.shields.io/badge/Images-Markdown%20%7C%20HTML-informational?style=flat-square" alt="Markdown and HTML images">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="MIT License"></a>
</p>

<p align="center">
  <a href="README.md">English</a> | 简体中文
</p>

一条命令，把 Markdown 文件里的所有图片搬到你的图床。`image-migrate-picgo` 通过 [PicGo](https://github.com/Molunerfinn/PicGo) 上传图片，并把文件中的图片地址替换为上传后的 URL。

适用场景：

- 发布引用了本地图片的笔记；
- 把图片从一个图床迁移到另一个图床；
- 把内嵌的 Base64（Data URL）图片换成普通链接。

## 功能

- **支持各种图片来源**：本地文件、HTTP/HTTPS 链接、图片 Data URL。
- **支持各种图片写法**：Markdown 行内图片、引用式图片、HTML `<img>` 标签。
- **两种上传方式**：PicGo Server（PicGo 桌面应用）或 PicGo CLI（npm 包 `picgo`）。
- **安全改写**：不会改动代码块、行内代码和普通链接；所有图片都上传成功后才写入文件。
- **不重复上传**：同一张图片被引用多次，只上传一次。

## 示例

迁移前：

```markdown
![架构图](images/architecture.png "概览")
![Logo][logo]
<img src="https://old-host.example.com/screenshot.png" width="600">

[logo]: ./images/logo.png
```

运行 `image-migrate-picgo notes.md` 后：

```markdown
![架构图](<https://cdn.example.com/architecture.png> "概览")
![Logo](<https://cdn.example.com/logo.png>)
<img src="https://cdn.example.com/screenshot.png" width="600">

[logo]: ./images/logo.png
```

## 安装

需要 Python 3.11 或更新版本。

```bash
pip install image-migrate-picgo
```

此外，还需要在 PicGo Server 或 PicGo CLI 中配置好图床，见[上传方式](#上传方式)。

## 快速开始

1. 打开 PicGo 桌面应用，配置图床，并在设置中开启 **PicGo Server**。
2. 迁移文件：

   ```bash
   image-migrate-picgo notes.md
   ```

> [!WARNING]
> 默认会**直接修改原 Markdown 文件**。请先提交到 Git 或备份，也可以用 `--output` 写入新文件：
>
> ```bash
> image-migrate-picgo notes.md --output notes.migrated.md
> ```

## 上传方式

### PicGo Server（默认）

使用 PicGo 桌面应用内置的 HTTP 服务，默认地址为 `http://127.0.0.1:36677/upload`。

```bash
# 自定义地址
image-migrate-picgo notes.md --server-url http://127.0.0.1:36677/upload

# PicGo Server 设置了访问密钥
image-migrate-picgo notes.md --server-secret <secret>
```

### PicGo CLI

使用 [PicGo-Core](https://github.com/PicGo/PicGo-Core) 命令行工具。不需要桌面应用，适合服务器和 CI 环境。

```bash
npm install picgo -g

# 配置图床（交互式向导）
image-migrate-picgo --configure

# 通过 PicGo CLI 上传
image-migrate-picgo notes.md --method cli
```

配置默认保存在 `~/.picgo/config.json`。如果配置文件不存在，使用 `--method cli` 时会自动启动配置向导。

## 命令行参数

```text
image-migrate-picgo [OPTIONS] [MARKDOWN]
```

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `MARKDOWN` | 要迁移的 Markdown 文件 | — |
| `-o`, `--output PATH` | 把结果写入该文件，而不是修改 `MARKDOWN` | 修改原文件 |
| `--method [server\|cli]` | 上传方式 | `server` |
| `--server-url TEXT` | PicGo Server 上传地址 | `http://127.0.0.1:36677/upload` |
| `--server-secret TEXT` | PicGo Server 访问密钥，以 Bearer Token 发送 | — |
| `--picgo-command PATH` | PicGo CLI 可执行文件 | 从 `PATH` 查找 `picgo` |
| `--picgo-config PATH` | PicGo CLI 配置文件 | `~/.picgo/config.json` |
| `--configure` | 启动 PicGo 图床配置向导后退出 | — |

## Python API

```python
from image_migrate_picgo import CliUploader, ServerUploader, migrate_markdown

result = migrate_markdown(
    "notes.md",
    ServerUploader(),  # 或 CliUploader()
    output_path="notes.migrated.md",  # 省略则直接修改 notes.md
)

print(result.output_path)  # 结果写入的路径
print(result.migrated_images)  # 改写的图片引用数
print(result.uploaded_images)  # 上传的图片数（去重后）
print(result.urls)  # 上传后的 URL
```

## LICENSE

本项目使用 [MIT License](LICENSE)。
