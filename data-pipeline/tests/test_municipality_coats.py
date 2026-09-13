"""Check attribution safety and missing-image behavior."""

import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))
spec = importlib.util.spec_from_file_location("municipality_pages", PIPELINE_DIR / "36-generate-municipality-pages.py")
pages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pages)


class MunicipalityCoatTests(unittest.TestCase):
    def test_source_metadata_is_escaped_and_permission_links_are_filtered(self):
        credit = pages.coat_credit({
            "title": "<script>title</script>", "author": "A & B",
            "page_url": "https://commons.wikimedia.org/wiki/File:Example.svg",
            "license": "CC BY-SA 4.0", "license_url": "javascript:alert(1)",
            "credit": "<img src=x onerror=alert(1)>",
            "commons_metadata": {"Permission": {"value":
                '<a href="javascript:alert(1)">bad</a><a href="https://example.org/permission">permission</a>'}},
        })
        self.assertNotIn("<script>", credit)
        self.assertNotIn("<img", credit)
        self.assertNotIn("javascript:", credit)
        self.assertIn("A &amp; B", credit)
        self.assertIn('href="https://example.org/permission"', credit)

    def test_missing_and_ambiguous_records_show_placeholder_without_fake_download(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "municipalities-web").mkdir()
            (root / "municipalities-web/placeholder.webp").write_bytes(b"prepared-placeholder")
            for record in (None, {"status": "no_coat_of_arms"}, {"status": "ambiguous_coat_of_arms"}):
                files = {}
                image, download, filename = pages.municipality_coat(record, 1, files, root)
                self.assertEqual(filename, "placeholder.webp")
                self.assertIn("unavailable", image)
                self.assertNotIn("<a", download)
                self.assertEqual(files[Path("municipalities/placeholder.webp")], b"prepared-placeholder")


if __name__ == "__main__":
    unittest.main()
