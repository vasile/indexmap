"""Regression checks for sitemap URLs and current versus dated page metadata."""

import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

from config.loader import PIPELINE, REFERENCE_DATE
from site_helpers import canonical_url, publish_pinned_release, site_url

spec = importlib.util.spec_from_file_location("generate_seo", PIPELINE_DIR / "38-generate-seo.py")
seo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seo)


def page(path):
    return (f'<!doctype html><html><head><link rel="canonical" href="{canonical_url(path)}">'
            '</head><body><a href="../">Country</a></body></html>').encode()


class SeoTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        for path in ("index.html", "countries/index.html", "countries/ch.html", "cantons/index.html",
                     "cantons/zh.html", "districts/index.html", "municipalities/index.html"):
            target = self.output / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(page(path))

    def test_sitemap_uses_unique_canonical_html_urls(self):
        dated = self.output / "versions/2020-01-01/countries"
        dated.mkdir(parents=True)
        (dated / "old.html").write_bytes(b"archived page")
        (self.output / "countries/ch.geojson").write_bytes(b"boundary download")
        (self.output / "countries/countries.zip").write_bytes(b"zip download")

        self.assertEqual(seo.build(self.output), 6)
        sitemap = self.output / "sitemap.xml"
        first = sitemap.read_bytes()
        xml = ET.fromstring(first)
        self.assertEqual(xml.tag, "{http://www.sitemaps.org/schemas/sitemap/0.9}urlset")
        urls = [element.text for element in xml.findall("{*}url/{*}loc")]
        self.assertEqual(urls, [
            "https://indexmap.ch/", "https://indexmap.ch/cantons/", "https://indexmap.ch/cantons/zh.html",
            "https://indexmap.ch/countries/ch.html", "https://indexmap.ch/districts/",
            "https://indexmap.ch/municipalities/",
        ])
        self.assertEqual(xml.findall(".//{*}lastmod"), [])
        self.assertEqual((self.output / "robots.txt").read_text(),
                         "User-agent: *\nAllow: /\n\nSitemap: https://indexmap.ch/sitemap.xml\n")
        seo.build(self.output)
        self.assertEqual(sitemap.read_bytes(), first)

    def test_incomplete_build_does_not_replace_existing_seo_files(self):
        (self.output / "sitemap.xml").write_text("previous sitemap")
        (self.output / "robots.txt").write_text("previous robots")
        (self.output / "municipalities/index.html").unlink()
        with self.assertRaisesRegex(ValueError, "generate all current pages"):
            seo.build(self.output)
        self.assertEqual((self.output / "sitemap.xml").read_text(), "previous sitemap")
        self.assertEqual((self.output / "robots.txt").read_text(), "previous robots")

    def test_missing_duplicate_or_wrong_canonical_fails(self):
        for content in (b"<html><head></head></html>", page("cantons/zh.html") * 2,
                        page("cantons/zh.html").replace(b"https://indexmap.ch", b"http://localhost:8080")):
            with self.subTest(content=content):
                (self.output / "cantons/zh.html").write_bytes(content)
                with self.assertRaisesRegex(ValueError, "Invalid canonical URL"):
                    seo.build(self.output)

    def test_dated_pages_refer_to_their_own_release(self):
        files = {Path("countries/index.html"): page("countries/index.html"),
                 Path("countries/ch.html"): page("countries/ch.html")}
        publish_pinned_release(self.output, files, "countries")
        dated = self.output / "versions" / REFERENCE_DATE / "countries"
        for name, suffix in (("index.html", ""), ("ch.html", "ch.html")):
            text = (dated / name).read_text()
            self.assertEqual(seo.PageCanonical(text).urls,
                             [f"https://indexmap.ch/versions/{REFERENCE_DATE}/countries/{suffix}"])
            self.assertIn('href="../countries/"', text)
        original = (dated / "ch.html").read_bytes()
        files[Path("countries/ch.html")] = b"new current content"
        publish_pinned_release(self.output, files, "countries")
        self.assertEqual((dated / "ch.html").read_bytes(), original)

    def test_origin_must_be_https_at_domain_root(self):
        for origin in ("http://indexmap.ch", "https://indexmap.ch/subpath", "https://user:pass@indexmap.ch",
                       "https://indexmap.ch?preview=yes", "https://indexmap.ch/#home"):
            with self.subTest(origin=origin), patch.dict(PIPELINE, {"site_url": origin}):
                with self.assertRaises(ValueError):
                    site_url("sitemap.xml")


if __name__ == "__main__":
    unittest.main()
