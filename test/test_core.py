import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

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


class MigrateTest(unittest.TestCase):
    def test_missing_output_directory_fails_before_upload(self) -> None:
        uploads: list[list[str | Path]] = []

        class RecordingUploader:
            def upload(self, sources):
                uploads.append(list(sources))
                return ["https://cdn.example/image.png"] * len(sources)

        with TemporaryDirectory(prefix="image-test-", dir="test") as name:
            document = Path(name) / "document.md"
            document.write_text("![Logo](https://example.com/logo.png)\n")

            with self.assertRaisesRegex(FileNotFoundError, "输出目录不存在"):
                migrate_markdown(
                    document,
                    RecordingUploader(),
                    output_path=Path(name) / "missing" / "document.md",
                )

            self.assertEqual(uploads, [])
            self.assertEqual(
                document.read_text(), "![Logo](https://example.com/logo.png)\n"
            )


if __name__ == "__main__":
    unittest.main()
