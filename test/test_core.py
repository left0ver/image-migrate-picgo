import re
import unittest
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

from image_migrate_picgo import image_sources, migrate_markdown, rewrite_markdown
from image_migrate_picgo.core import _upload_source


class MarkdownTest(unittest.TestCase):
    def test_finds_inline_and_reference_images(self) -> None:
        content = """![local](images/a.png)
![remote][logo]

[logo]: https://example.com/logo.png
"""

        self.assertEqual(
            image_sources(content),
            ["images/a.png", "https://example.com/logo.png"],
        )

    def test_ignores_code_and_regular_links(self) -> None:
        content = """[link](image.png)
`![code](code.png)`

```md
![block](block.png)
```

![data](data:image/png;base64,AAAA)
"""

        self.assertEqual(
            image_sources(content),
            ["data:image/png;base64,AAAA"],
        )

    def test_rewrites_only_parsed_images(self) -> None:
        content = """![local](images/a.png "title")
![remote][logo]
[link](images/a.png)
`![code](images/a.png)`

[logo]: https://example.com/logo.png
"""

        rewritten = rewrite_markdown(
            content,
            {
                "images/a.png": "https://cdn.example/a.png",
                "https://example.com/logo.png": "https://cdn.example/logo.png",
            },
        )

        self.assertIn('![local](<https://cdn.example/a.png> "title")', rewritten)
        self.assertIn("![remote](<https://cdn.example/logo.png>)", rewritten)
        self.assertIn("[link](images/a.png)", rewritten)
        self.assertIn("`![code](images/a.png)`", rewritten)

    def test_preserves_escaped_alt_text(self) -> None:
        content = r"![a\]b](image.png)"

        rewritten = rewrite_markdown(
            content,
            {"image.png": "https://cdn.example/image.png"},
        )

        self.assertEqual(rewritten, r"![a\]b](<https://cdn.example/image.png>)")

    def test_finds_and_rewrites_html_images(self) -> None:
        content = """<img src="images/a.png" alt="A" width="600">
<img
  src="https://example.com/banner.png"
  alt="Banner"
/>

`<img src="code.png">`

```html
<img src="block.png">
```
"""

        self.assertEqual(
            image_sources(content),
            ["images/a.png", "https://example.com/banner.png"],
        )
        rewritten = rewrite_markdown(
            content,
            {
                "images/a.png": "https://cdn.example/a.png",
                "https://example.com/banner.png": "https://cdn.example/banner.png",
            },
        )

        self.assertIn(
            '<img src="https://cdn.example/a.png" alt="A" width="600">',
            rewritten,
        )
        self.assertIn(
            '<img src="https://cdn.example/banner.png" alt="Banner" />',
            rewritten,
        )
        self.assertIn('`<img src="code.png">`', rewritten)
        self.assertIn('<img src="block.png">', rewritten)

    def test_decodes_data_image(self) -> None:
        source = "data:image/png;base64,iVBORw0KGgo="
        with TemporaryDirectory(prefix="image-test-", dir="test") as name:
            path = _upload_source(
                source,
                Path("test/document.md"),
                Path(name),
                0,
            )

            self.assertIsInstance(path, Path)
            self.assertEqual(path.suffix, ".png")
            self.assertEqual(path.read_bytes(), b"\x89PNG\r\n\x1a\n")

    def test_passes_remote_images_as_urls(self) -> None:
        with TemporaryDirectory(prefix="image-test-", dir="test") as name:
            directory = Path(name)
            source = "https://example.com/image.png?size=2"

            self.assertEqual(
                _upload_source(source, Path("test/document.md"), directory, 0),
                source,
            )
            self.assertEqual(
                _upload_source(
                    "//example.com/image.png",
                    Path("test/document.md"),
                    directory,
                    1,
                ),
                "https://example.com/image.png",
            )
            self.assertEqual(list(directory.iterdir()), [])


PIXEL_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
TIMESTAMP_NAME_RE = re.compile(r"\d{15}")


class RecordingUploader:
    """记录上传时收到的来源；临时文件在上传后会被删除，所以同时保存文件内容。"""

    def __init__(self) -> None:
        self.sources: list[str | Path] = []
        self.contents: list[bytes | None] = []

    def upload(self, sources):
        for source in sources:
            self.sources.append(source)
            self.contents.append(
                source.read_bytes() if isinstance(source, Path) else None
            )
        return [f"https://cdn.example/{index}.png" for index in range(len(sources))]


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args) -> None:
        pass


class MigrateTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = TemporaryDirectory(prefix="image-test-", dir="test")
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        images = self.directory / "images"
        images.mkdir()
        self.image = images / "sun.svg"
        self.image.write_bytes(b"<svg>sun</svg>")
        self.remote_image = images / "remote.svg"
        self.remote_image.write_bytes(b"<svg>remote</svg>")

        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), partial(_QuietHandler, directory=images)
        )
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        Thread(target=server.serve_forever, daemon=True).start()
        self.remote_url = f"http://127.0.0.1:{server.server_port}/remote.svg"

        self.document = self.directory / "document.md"
        self.document.write_text(
            f"![太阳](images/sun.svg)\n\n![远程]({self.remote_url})\n\n"
            f"![像素]({PIXEL_DATA_URL})\n\n![太阳二](images/sun.svg)\n",
            encoding="utf-8",
        )

    def test_renames_images_to_timestamps_before_upload(self) -> None:
        uploader = RecordingUploader()

        result = migrate_markdown(self.document, uploader)

        names = [Path(source).stem for source in uploader.sources]
        self.assertEqual(
            [Path(source).suffix for source in uploader.sources],
            [".svg", ".svg", ".png"],
        )
        for name in names:
            self.assertRegex(name, TIMESTAMP_NAME_RE)
        self.assertEqual([int(name) - int(names[0]) for name in names], [0, 1, 2])
        self.assertEqual(
            uploader.contents[:2], [b"<svg>sun</svg>", b"<svg>remote</svg>"]
        )
        self.assertTrue(uploader.contents[2].startswith(b"\x89PNG"))
        self.assertEqual(
            result.urls, tuple(f"https://cdn.example/{i}.png" for i in range(3))
        )
        self.assertEqual(
            self.document.read_text(encoding="utf-8"),
            "![太阳](<https://cdn.example/0.png>)\n\n"
            "![远程](<https://cdn.example/1.png>)\n\n"
            "![像素](<https://cdn.example/2.png>)\n\n"
            "![太阳二](<https://cdn.example/0.png>)\n",
        )
        self.assertEqual(self.image.read_bytes(), b"<svg>sun</svg>")
        self.assertEqual(list(self.directory.glob(".image-migrate-picgo-*")), [])

    def test_keeps_original_names_without_rename(self) -> None:
        uploader = RecordingUploader()

        migrate_markdown(self.document, uploader, rename=False)

        self.assertEqual(uploader.sources[0], self.image.resolve())
        self.assertEqual(uploader.sources[1], self.remote_url)
        self.assertEqual(Path(uploader.sources[2]).name, "data-2.png")

    def test_missing_output_directory_fails_before_upload(self) -> None:
        uploader = RecordingUploader()
        original = self.document.read_text(encoding="utf-8")

        with self.assertRaisesRegex(FileNotFoundError, "输出目录不存在"):
            migrate_markdown(
                self.document,
                uploader,
                output_path=self.directory / "missing" / "document.md",
            )

        self.assertEqual(uploader.sources, [])
        self.assertEqual(self.document.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
