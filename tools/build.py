#!/usr/bin/env python3
"""Rank&Rent static site builder — stdlib only.

Usage:
  python3 tools/build.py sites/<site-id> [--base /subpath] [--url https://...] [--out DIR] [--noindex]

Reads sites/<id>/site.json + src/pages/*.html (+ <!--META ...--> headers),
renders tools/templates/base.html, emits static HTML, sitemap.xml, robots.txt.
Exit code != 0 on validation errors (unreplaced placeholders, broken internal
links, invalid JSON-LD, nav refs to missing pages).
"""
import argparse
import datetime as dt
import html as htmllib
import json
import re
import shutil
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "tools" / "templates"

META_RE = re.compile(r"^<!--META\s*(.*?)\s*-->\s*", re.DOTALL)
PLACEHOLDER_RE = re.compile(r"\{\{([A-Z_0-9]+)\}\}")
FAQ_RE = re.compile(
    r'<details class="faq">\s*<summary>(.*?)</summary>\s*'
    r'<div class="faq-a">(.*?)</div>\s*</details>', re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
H2_ANCHOR_RE = re.compile(r'<section class="section" id="([^"]+)">')


def die(msg):
    print(f"BUILD ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def warn(msg):
    print(f"  warn: {msg}")


def strip_tags(s):
    return TAG_RE.sub("", s).strip()


def load_page(path: Path):
    raw = path.read_text(encoding="utf-8")
    meta = {}
    m = META_RE.match(raw)
    if m:
        try:
            meta = json.loads(m.group(1))
        except json.JSONDecodeError as e:
            die(f"{path.name}: META JSON invalido: {e}")
        raw = raw[m.end():]
    return meta, raw.strip()


def page_slug_dir(path: Path) -> str:
    """index.html -> '' ; foo.html -> 'foo/' (pretty URLs)."""
    if path.name == "index.html":
        return ""
    return path.stem + "/"


def esc(s):
    return htmllib.escape(s, quote=True)


def build():
    ap = argparse.ArgumentParser()
    ap.add_argument("site_dir", help="es. sites/fabbro-padova")
    ap.add_argument("--base", default="", help="path prefix, es. /fabbro-padova (default: nessuno)")
    ap.add_argument("--url", default="", help="canonical origin, es. https://francescowm.github.io/rankandrent-sites")
    ap.add_argument("--out", default=None)
    ap.add_argument("--noindex", action="store_true", help="meta robots noindex (anteprime)")
    args = ap.parse_args()

    site_dir = Path(args.site_dir)
    if not site_dir.is_dir():
        die(f"{site_dir} non trovata")
    cfg = json.loads((site_dir / "site.json").read_text(encoding="utf-8"))
    out = Path(args.out) if args.out else site_dir / "dist"
    base = args.base.rstrip("/")
    origin = args.url.rstrip("/")

    pages_dir = site_dir / "src" / "pages"
    pages = sorted(pages_dir.glob("*.html"))
    if not pages:
        die("nessuna pagina in src/pages")

    tpl = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    today = dt.date.today().isoformat()

    # ---- nav -------------------------------------------------------------
    nav_items = []
    footer_items = []
    for item in cfg["nav"]:
        href = (base + item["href"]) if item["href"] != "/" else (base + "/")
        nav_items.append(f'<a href="{esc(href)}">{esc(item["label"])}</a>')
    for item in cfg["nav"][1:]:  # footer senza home
        href = base + item["href"]
        footer_items.append(f'<a href="{esc(href)}">{esc(item["label"])}</a>')
    nav_html = "\n".join(nav_items)
    footer_html = "\n".join(footer_items)

    # ---- local business schema (globale, ogni pagina) ---------------------
    schema_type = cfg.get("schema_type", "Locksmith")
    lb = {
        "@type": schema_type,
        "@id": origin + base + "/#business",
        "name": cfg["brand"],
        "description": cfg["tagline"],
        "url": origin + base + "/",
        "telephone": cfg["phone"],
        "email": cfg["email"],
        "priceRange": cfg["price_range"],
        "openingHours": cfg["opening_hours"],
        "address": {
            "@type": "PostalAddress",
            "addressLocality": cfg["city"],
            "addressRegion": cfg["region"],
            "addressCountry": "IT",
        },
        "areaServed": {
            "@type": "GeoCircle",
            "geoMidpoint": {"@type": "GeoCoordinates",
                            "latitude": cfg["geo"]["lat"],
                            "longitude": cfg["geo"]["lng"]},
            "geoRadius": cfg["area_served_radius_km"] * 1000,
        },
    }
    schema_global = ('<script type="application/ld+json">\n'
                     + json.dumps({"@context": "https://schema.org", "@graph": [lb]},
                                  ensure_ascii=False, indent=1)
                     + "\n</script>")

    # ---- prepara out ------------------------------------------------------
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / "assets").mkdir()

    sitemap_urls = []
    internal_links = []  # (src_page, href) da validare

    for p in pages:
        meta, body = load_page(p)
        slug = page_slug_dir(p)
        page_url_path = base + "/" + slug
        canonical = origin + page_url_path

        # breadcrumb visibile + schema
        label = meta.get("nav_label") or p.stem.replace("-", " ").capitalize()
        crumb = (
            f'<nav class="breadcrumbs" aria-label="Percorso">'
            f'<ol><li><a href="{esc(base)}/">{esc(cfg["brand"])}</a></li>'
            f'<li aria-current="page">{esc(label)}</li></ol></nav>'
        ) if slug else ""

        # schema pagina
        graph = [{
            "@type": "WebPage",
            "@id": canonical + "#webpage",
            "url": canonical,
            "name": meta["title"],
            "description": meta["description"],
            "isPartOf": {"@id": origin + base + "/#business"},
            "inLanguage": "it-IT",
        }]
        extra = dict(meta.get("schema_extra") or {})
        if extra:
            types = extra.pop("@type")
            if isinstance(types, str):
                types = [types]
            if "WebPage" in types:
                remaining = [t for t in types if t != "WebPage"]
                graph[0].update(extra)
                if remaining:
                    graph[0]["@type"] = ["WebPage"] + remaining
            elif types:
                node = {"@type": types[0] if len(types) == 1 else types,
                        "provider": {"@id": origin + base + "/#business"}}
                node.update(extra)
                graph.append(node)
        # FAQ
        faqs = [(strip_tags(q), TAG_RE.sub(" ", a).strip())
                for q, a in FAQ_RE.findall(body)]
        if faqs:
            graph.append({
                "@type": "FAQPage",
                "@id": canonical + "#faq",
                "mainEntity": [
                    {"@type": "Question", "name": q,
                     "acceptedAnswer": {"@type": "Answer", "text": a}}
                    for q, a in faqs
                ],
            })
        if slug:
            graph.append({
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": cfg["brand"],
                     "item": origin + base + "/"},
                    {"@type": "ListItem", "position": 2, "name": label,
                     "item": canonical},
                ],
            })
        schema_page = ('<script type="application/ld+json">\n'
                       + json.dumps({"@context": "https://schema.org",
                                     "@graph": graph},
                                    ensure_ascii=False, indent=1)
                       + "\n</script>")

        values = {
            "TITLE": meta["title"],
            "META_DESCRIPTION": meta["description"],
            "CANONICAL": canonical,
            "NOINDEX": '<meta name="robots" content="noindex">\n' if args.noindex else "",
            "GA4_HEAD": "",
            "SCHEMA_GLOBAL": schema_global,
            "SCHEMA_PAGE": schema_page,
            "BODY": body,
            "NAV": nav_html,
            "FOOTER_LINKS": footer_html,
            "BREADCRUMB": crumb,
            "BRAND": cfg["brand"],
            "TAGLINE": cfg["tagline"],
            "CITY": cfg["city"],
            "LEGAL_NOTE": cfg["legal_note"],
            "YEAR": str(cfg["year"]),
            "PHONE": cfg["phone"],
            "PHONE_DISPLAY": cfg["phone_display"],
            "EMAIL": cfg["email"],
            "GA4_ID": cfg["ga4_id"],
            "BASE": base,
            "FORM_ACTION": cfg.get("form_action", "#"),
        }

        # link interni dal body grezzo (placeholder BASE non ancora risolti)
        internal_links.extend(
            (p.name, m) for m in re.findall(r'href="\{\{BASE\}\}[^"]*"', body))

        html = tpl
        # placeholders pagina (BASE ecc.) prima di quelli globali
        for k, v in values.items():
            html = html.replace("{{" + k + "}}", str(v))

        leftover = PLACEHOLDER_RE.findall(html)
        if leftover:
            die(f"{p.name}: placeholder non risolti: {sorted(set(leftover))}")

        dest_dir = out / slug
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "index.html").write_text(html, encoding="utf-8")
        sitemap_urls.append(canonical)

    # ---- assets ------------------------------------------------------------
    shutil.copy(TEMPLATES / "style.css", out / "assets" / "style.css")

    # ---- sitemap + robots ---------------------------------------------------
    sitemap = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
    for u in sitemap_urls:
        sitemap += f"  <url><loc>{esc(u)}</loc><lastmod>{today}</lastmod></url>\n"
    sitemap += "</urlset>\n"
    (out / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    robots = f"User-agent: *\nAllow: /\nSitemap: {origin}{base}/sitemap.xml\n"
    (out / "robots.txt").write_text(robots, encoding="utf-8")

    # ---- validazioni --------------------------------------------------------
    errors = []
    # nav → pagina esiste
    page_dirs = {p.stem for p in pages}
    for item in cfg["nav"]:
        want = "" if item["href"] == "/" else item["href"].strip("/")
        if want and want not in page_dirs:
            errors.append(f"nav '{item['href']}' non corrisponde ad alcuna pagina")
    # link interni → pagina destinazione esiste (+ ancora se presente)
    for src, href in internal_links:
        target = href[len('href="{{BASE}}'):]
        anchor = ""
        if "#" in target:
            target, anchor = target.split("#", 1)
        target = target.strip('/" ')
        if target == "":
            continue  # link home
        if target not in page_dirs:
            errors.append(f"{src}: link interno rotto → {href}")
        elif anchor:
            anchor = anchor.strip('"')
            tgt_body = (pages_dir / f"{target}.html").read_text(encoding="utf-8")
            if f'id="{anchor}"' not in tgt_body:
                errors.append(f"{src}: ancora #{anchor} assente in {target}.html")
    # title/meta lunghezza (warning)
    for p in pages:
        meta, _ = load_page(p)
        t, d = meta["title"], meta["description"]
        if len(t) > 65:
            warn(f"{p.name}: title {len(t)} char (>65)")
        if len(d) > 165:
            warn(f"{p.name}: description {len(d)} char (>165)")

    if errors:
        for e in errors:
            print(f"BUILD ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"OK: {len(pages)} pagine → {out} (base='{base}', url='{origin or '(nessuno)'}')")
    for u in sitemap_urls:
        print("  " + u)


if __name__ == "__main__":
    build()
