import unittest
from pathlib import Path

from image_migrate_picgo import image_sources
from image_migrate_picgo.core import _upload_source

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "markdown"
EXPECTED_IMAGES = {
    "01-inline.md": 2,
    "02-reference.md": 2,
    "03-html.md": 2,
    "04-code.md": 2,
    "05-duplicates.md": 4,
    "06-nested.md": 2,
    "07-unicode.md": 2,
    "08-structure.md": 4,
    "09-url-forms.md": 2,
    "10-data-url.md": 3,
}


class FixtureTest(unittest.TestCase):
    def test_markdown_files_have_local_and_remote_images(self) -> None:
        documents = sorted(FIXTURE_DIRECTORY.rglob("*.md"))
        self.assertEqual(
            {document.name for document in documents}, EXPECTED_IMAGES.keys()
        )

        for document in documents:
            with self.subTest(document=document.name):
                sources = image_sources(document.read_text(encoding="utf-8"))
                local = [
                    source
                    for source in sources
                    if not source.startswith(("http://", "https://", "//", "data:"))
                ]
                remote = [
                    source
                    for source in sources
                    if source.startswith(("http://", "https://", "//"))
                ]

                self.assertEqual(len(sources), EXPECTED_IMAGES[document.name])
                self.assertTrue(local)
                self.assertTrue(remote)
                for source in local:
                    path = _upload_source(source, document, document.parent, 0)
                    self.assertIsInstance(path, Path)
                    self.assertEqual(path.suffix, ".svg")
                    self.assertTrue(path.is_file())


if __name__ == "__main__":
    unittest.main()
