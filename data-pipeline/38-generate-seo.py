#!/usr/bin/env python3
"""Generate sitemap.xml and robots.txt from the current, fully rendered site."""

import argparse
from html.parser import HTMLParser
from pathlib import Path
import xml.etree.ElementTree as ET

from config.loader import DIST_DIR, SITE_DIR
from site_helpers import canonical_url, site_url

REQUIRED_SECTIONS = ("countries", "cantons", "districts", "municipalities")
EXCLUDED_ROOTS = {"versions"}
SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"


class PageCanonical(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.urls = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "link" and "canonical" in attrs.get("rel", "").lower().split():
            self.urls.append(attrs.get("href"))


def build(output_dir: Path) -> int:
    required = [Path("index.html"), *(Path(section) / "index.html" for section in REQUIRED_SECTIONS)]
    for path in required:
        if not (output_dir / path).is_file():
            raise ValueError(f"Missing {path}; generate all current pages with steps 30–36 first")

    # Discover pages instead of maintaining a list of route folders. This keeps
    # the sitemap complete when a new current page or section is introduced.
    # Historical snapshots are intentionally not current, indexable pages.
    pages = [path.relative_to(output_dir) for path in sorted(output_dir.rglob("*.html"))
             if path.relative_to(output_dir).parts[0] not in EXCLUDED_ROOTS]
    urls = set()
    for path in pages:
        expected = canonical_url(path)
        actual = PageCanonical((output_dir / path).read_text(encoding="utf-8")).urls
        if actual != [expected]:
            raise ValueError(f"Invalid canonical URL in {path}; regenerate the page before building SEO files")
        urls.add(expected)
    if len(urls) > 50_000:
        raise ValueError("More than 50,000 URLs; split the sitemap before publishing")

    ET.register_namespace("", SITEMAP_NAMESPACE)
    sitemap = ET.Element(f"{{{SITEMAP_NAMESPACE}}}urlset")
    for url in sorted(urls):
        entry = ET.SubElement(sitemap, f"{{{SITEMAP_NAMESPACE}}}url")
        ET.SubElement(entry, f"{{{SITEMAP_NAMESPACE}}}loc").text = url
    ET.indent(sitemap, space="  ")
    xml = ET.tostring(sitemap, encoding="utf-8", xml_declaration=True) + b"\n"
    if len(xml) > 50 * 1024 * 1024:
        raise ValueError("Sitemap exceeds 50 MB; split it before publishing")
    robots = f"User-agent: *\nAllow: /\n\nSitemap: {site_url('sitemap.xml')}\n"
    llms = (SITE_DIR / "llms.txt").read_bytes()

    # Validate the complete site before replacing any published discovery file.
    (output_dir / "sitemap.xml").write_bytes(xml)
    (output_dir / "robots.txt").write_text(robots, encoding="utf-8")
    (output_dir / "llms.txt").write_bytes(llms)
    print(f"Generated sitemap.xml with {len(urls)} URLs, robots.txt and llms.txt in {output_dir}")
    return len(urls)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DIST_DIR)
    args = parser.parse_args()
    try:
        build(args.output_dir)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"SEO generation failed: {error}\n")


if __name__ == "__main__":
    main()
