#!/usr/bin/env python3
import os
import re
import json
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

SITEMAP_URL = "https://promptplum.com/ai_prompt-sitemap.xml"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal-archive-bot/1.0)"}
_HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(_HERE, "promptplum_prompts.json")
FAIL_LOG = os.path.join(_HERE, "promptplum_failures.log")
WORKERS = 6
TIMEOUT = 20


def unesc(s):
    return json.loads('"' + s + '"')


def get_pushes(html):
    matches = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.S)
    out = []
    for m in matches:
        try:
            out.append(unesc(m))
        except Exception:
            continue
    return out


def find_row_content(buffer, target_id):
    pattern = re.compile(r'(?:^|\D)' + re.escape(target_id) + r':T([0-9a-f]+),')
    m = pattern.search(buffer)
    if not m:
        return None
    hexlen = int(m.group(1), 16)
    start = m.end()
    b = buffer[start:].encode("utf-8")[:hexlen]
    try:
        return b.decode("utf-8", errors="strict")
    except Exception:
        return b.decode("utf-8", errors="replace")


def parse_page(html, url):
    pushes = get_pushes(html)
    buffer = "".join(pushes)
    data_chunk = None
    for real in pushes:
        if '"promptText"' in real and '"slug"' in real:
            m = re.search(r'^[0-9a-f]+:(\[.*)$', real, re.S)
            if m:
                data_chunk = m.group(1)
                break
    if not data_chunk:
        return None
    try:
        obj = json.loads(data_chunk)
    except Exception:
        return None
    rec = None
    for el in obj:
        if isinstance(el, list) and len(el) >= 4 and isinstance(el[3], dict) and "data" in el[3]:
            rec = el[3]["data"]
            break
    if rec is None:
        return None
    full_prompt = rec.get("promptText")
    fp_ref = rec.get("fullPrompt")
    if isinstance(fp_ref, str) and re.fullmatch(r"\$[0-9a-f]+", fp_ref):
        resolved = find_row_content(buffer, fp_ref[1:])
        if resolved:
            full_prompt = resolved
    elif isinstance(fp_ref, str) and fp_ref:
        full_prompt = fp_ref
    return {
        "url": url,
        "slug": rec.get("slug"),
        "title": rec.get("title"),
        "category": rec.get("category"),
        "aiTools": rec.get("aiTools"),
        "image": rec.get("image"),
        "likeCount": rec.get("likeCount"),
        "promptText": full_prompt,
    }


def get_sitemap_urls():
    r = requests.get(SITEMAP_URL, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return re.findall(r"<loc>([^<]+)</loc>", r.text)


def fetch_one(url):
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 429:
                time.sleep(3 * (attempt + 1))
                continue
            r.raise_for_status()
            result = parse_page(r.text, url)
            return result
        except Exception as e:
            if attempt == 2:
                return {"url": url, "error": str(e)}
            time.sleep(1.5 * (attempt + 1))
    return {"url": url, "error": "exhausted retries"}


def main():
    urls = get_sitemap_urls()
    print(f"Found {len(urls)} URLs", file=sys.stderr)

    results = []
    failures = []
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(fetch_one, u): u for u in urls}
        for fut in as_completed(futures):
            res = fut.result()
            done += 1
            if res is None:
                failures.append(futures[fut])
            elif "error" in res:
                failures.append(res["url"])
            else:
                results.append(res)
            if done % 50 == 0:
                print(f"progress: {done}/{len(urls)}  ok={len(results)} fail={len(failures)}", file=sys.stderr)
                with open(OUT_PATH, "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    with open(FAIL_LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(failures))

    print(f"DONE. ok={len(results)} fail={len(failures)}", file=sys.stderr)


if __name__ == "__main__":
    main()
