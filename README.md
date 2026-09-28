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
  English | <a href="README.zh-CN.md">简体中文</a>
</p>

Move every image in a Markdown file to your image host with one command. `image-migrate-picgo` uploads the images through [PicGo](https://github.com/Molunerfinn/PicGo) and rewrites their links to the uploaded URLs.

It is useful when you want to:

- publish notes that reference local images,
- move images from one image host to another,
- replace inline Base64 (Data URL) images with regular links.

## Features

- **Every image source**: local files, HTTP/HTTPS URLs, and image Data URLs.
- **Every image syntax**: inline Markdown images, reference-style images, and HTML `<img>` tags.
- **Two upload methods**: PicGo Server (the PicGo desktop app) or PicGo CLI (`picgo` from npm).
- **Safe rewriting**: code blocks, inline code, and ordinary links stay untouched. The file is written only after every upload succeeds.
- **No duplicate uploads**: an image referenced several times is uploaded once.

## Example

Before:

```markdown
![Architecture](images/architecture.png "Overview")
![Logo][logo]
<img src="https://old-host.example.com/screenshot.png" width="600">

[logo]: ./images/logo.png
```

After running `image-migrate-picgo notes.md`:

```markdown
![Architecture](<https://cdn.example.com/architecture.png> "Overview")
![Logo](<https://cdn.example.com/logo.png>)
<img src="https://cdn.example.com/screenshot.png" width="600">

[logo]: ./images/logo.png
```

## Installation

Requires Python 3.11 or newer.

```bash
pip install image-migrate-picgo
```

You also need an image host configured in either PicGo Server or PicGo CLI (see [Upload methods](#upload-methods)).

## Quick start

1. Open the PicGo desktop app, configure an image host, and turn on **PicGo Server** in its settings.
2. Migrate a file:

   ```bash
   image-migrate-picgo notes.md
   ```

> [!WARNING]
> By default the Markdown file is **updated in place**. Commit or back it up first, or write the result to a new file with `--output`:
>
> ```bash
> image-migrate-picgo notes.md --output notes.migrated.md
> ```

## Upload methods

### PicGo Server (default)

Uses the HTTP server built into the PicGo desktop app, at `http://127.0.0.1:36677/upload` by default.

```bash
# Custom address
image-migrate-picgo notes.md --server-url http://127.0.0.1:36677/upload

# Server protected by a secret
image-migrate-picgo notes.md --server-secret <secret>
```

### PicGo CLI

Uses the [PicGo core](https://github.com/PicGo/PicGo-Core) command line tool. No desktop app is needed, which suits servers and CI.

```bash
npm install picgo -g

# Configure an uploader (an interactive wizard)
image-migrate-picgo --configure

# Upload through PicGo CLI
image-migrate-picgo notes.md --method cli
```

The configuration is saved to `~/.picgo/config.json` by default. If the configuration file does not exist, `--method cli` starts the wizard automatically.

## CLI options

```text
image-migrate-picgo [OPTIONS] [MARKDOWN]
```

| Option | Description | Default |
| --- | --- | --- |
| `MARKDOWN` | Markdown file to migrate | — |
| `-o`, `--output PATH` | Write the result to this file instead of updating `MARKDOWN` | Update in place |
| `--method [server\|cli]` | Upload method | `server` |
| `--server-url TEXT` | PicGo Server upload URL | `http://127.0.0.1:36677/upload` |
| `--server-secret TEXT` | PicGo Server secret, sent as a Bearer token | — |
| `--picgo-command PATH` | PicGo CLI executable | `picgo` on `PATH` |
| `--picgo-config PATH` | PicGo CLI configuration file | `~/.picgo/config.json` |
| `--rename` / `--no-rename` | Rename images to a timestamp before uploading, like the PicGo app's auto rename (e.g. `202609281430123.png`) | `--rename` |
| `--configure` | Run the PicGo uploader wizard and exit | — |

## Python API

```python
from image_migrate_picgo import CliUploader, ServerUploader, migrate_markdown

result = migrate_markdown(
    "notes.md",
    ServerUploader(),  # or CliUploader()
    output_path="notes.migrated.md",  # omit to update notes.md in place
    rename=False,  # keep original file names (default: rename to a timestamp)
)

print(result.output_path)  # where the result was written
print(result.migrated_images)  # image references rewritten
print(result.uploaded_images)  # unique images uploaded
print(result.urls)  # uploaded URLs
```

## LICENSE

This project is licensed under the [MIT License](LICENSE).
