"""Download news articles and keep only the article text (no menus, ads, footers).

Reads  data/raw/news/urls.txt   (one URL per line, '#' lines skipped)
Writes data/raw/news/articles/<id>.json  with url, title, date, site, text
Re-running skips articles already downloaded, so you can keep adding URLs.

Setup: uv add trafilatura
Run:   uv run python fetch_news.py
"""
import hashlib
import json
import time
from pathlib import Path

import trafilatura

URLS = Path("data/raw/news/urls.txt")
OUT = Path("data/raw/news/articles")


def article_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:12]   # short, stable file name per URL


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    urls = [u.strip() for u in URLS.read_text(encoding="utf-8").splitlines()
            if u.strip() and not u.startswith("#")]
    ok, skipped, failed = 0, 0, []

    for url in urls:
        path = OUT / f"{article_id(url)}.json"
        if path.exists():
            skipped += 1
            continue
        html = trafilatura.fetch_url(url)
        data = trafilatura.extract(html, output_format="json", with_metadata=True, url=url) if html else None
        if not data:
            failed.append(url)
            continue
        d = json.loads(data)
        if len(d.get("text") or "") < 500:        # paywalls / photo galleries give almost no text
            failed.append(url + "  (too little text)")
            continue
        article = {"url": url, "title": d.get("title"), "date": d.get("date"),
                   "site": d.get("hostname"), "text": d["text"]}
        path.write_text(json.dumps(article, ensure_ascii=False, indent=2), encoding="utf-8")
        ok += 1
        print(f"saved  {article['date']}  {article['title'][:70]}")
        time.sleep(1)                              # be polite to the sites

    print(f"\n{ok} saved, {skipped} already had, {len(failed)} failed")
    for f in failed:
        print("  FAILED", f)


if __name__ == "__main__":
    main()
