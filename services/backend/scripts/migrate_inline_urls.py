"""
migrate_inline_urls.py
DRY-RUN by default. Yalnizca rapor verir.

Eski inspection sonuclarinda result.image.url == "<inline>" kalmis kayitlari
tespit eder ve image_urls JSONB sutunundaki ilk URL ile patch'ler. Bu sayede
frontend history sayfasi thumbnail gosterebilir ve sonuc detay sayfasi gecerli
URL ile render edilir.

KULLANIM:
    # 1) DRY-RUN — neyi degistirecegini gor
    python services/backend/scripts/migrate_inline_urls.py

    # 2) Gercek migrasyon (yedek aldiktan sonra!)
    python services/backend/scripts/migrate_inline_urls.py --apply

ONEMLI:
    Veriye dokunmadan once `pg_dump` ile yedek alin. Bu script idempotent
    olsa da result JSONB'leri uretim verisidir.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any, Optional

import psycopg2
from psycopg2.extras import RealDictCursor


logger = logging.getLogger("migrate_inline_urls")


def _patch_inline(result: Any, image_urls: Optional[list]) -> tuple[Any, bool]:
    """result JSONB icindeki '<inline>' URL referanslarini image_urls ile değiştir.

    Returns:
        (patched_result, changed)
    """
    if not isinstance(result, dict):
        return result, False
    changed = False
    first_url = None
    if isinstance(image_urls, list) and image_urls:
        first = image_urls[0]
        if isinstance(first, str) and first and first != "<inline>":
            first_url = first

    img = result.get("image")
    if isinstance(img, dict) and img.get("url") == "<inline>":
        img["url"] = first_url
        changed = True

    # images: per-image listesi (yeni kontrat; eski kayitlarda yok)
    images_list = result.get("images")
    if isinstance(images_list, list):
        for i, entry in enumerate(images_list):
            if isinstance(entry, dict):
                url_i = image_urls[i] if (isinstance(image_urls, list) and i < len(image_urls)) else None
                if entry.get("url") == "<inline>":
                    entry["url"] = url_i
                    changed = True
                sub = entry.get("image")
                if isinstance(sub, dict) and sub.get("url") == "<inline>":
                    sub["url"] = url_i
                    changed = True

    return result, changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Gercek UPDATE calistir (DRY-RUN degil)")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="Postgres baglanti dizesi (default: DATABASE_URL env var)",
    )
    args = parser.parse_args()

    if not args.database_url:
        print("HATA: DATABASE_URL belirtilmedi. --database-url veya env var saglayin.", file=sys.stderr)
        return 2

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    conn = psycopg2.connect(args.database_url)
    conn.autocommit = False
    n_scanned = 0
    n_dirty = 0
    n_updated = 0
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT id, image_urls, result
                   FROM inspections
                   WHERE result::text LIKE '%<inline>%'"""
            )
            rows = cur.fetchall()

        for row in rows:
            n_scanned += 1
            iid = row["id"]
            image_urls = row.get("image_urls")
            if isinstance(image_urls, str):
                try:
                    image_urls = json.loads(image_urls)
                except Exception:
                    image_urls = None
            result = row.get("result")
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except Exception:
                    continue

            patched, changed = _patch_inline(result, image_urls)
            if changed:
                n_dirty += 1
                logger.info("DIRTY %s — image_urls=%s", iid, "yes" if image_urls else "EMPTY")
                if args.apply:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE inspections SET result = %s, updated_at = NOW() WHERE id = %s",
                            (json.dumps(patched), iid),
                        )
                        n_updated += 1

        if args.apply:
            conn.commit()
            logger.info("COMMIT: %d kayit guncellendi", n_updated)
        else:
            conn.rollback()
            logger.info("DRY-RUN bitti — scanned=%d, dirty=%d (uygulamak icin --apply)", n_scanned, n_dirty)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
