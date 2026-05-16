"""
scripts/export_openapi.py
FastAPI app'ten OpenAPI JSON cikar, packages/types/openapi.json'a yaz.

Bu, TS type generation icin referans dokuman saglar (TS tipleri zaten
elle yazili — packages/types/src altinda — ama OpenAPI'yi de sakliyoruz ki
otomatik client uretmek isteyen olursa kullanabilsin).

Kullanim:
    cd services/backend
    python scripts/export_openapi.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
BACKEND_DIR = HERE.parent
REPO_ROOT = BACKEND_DIR.parent.parent
OUT_PATH = REPO_ROOT / "packages" / "types" / "openapi.json"


def main():
    # Backend modullerini import edebilmek icin path ekle
    sys.path.insert(0, str(BACKEND_DIR))

    # ML yuklemesini bypass et — sadece schema lazim
    os.environ.setdefault("SKIP_ML_LOAD", "1")

    # Stub ml_service - dummy pipeline ile import et
    try:
        from main import app  # noqa: E402
    except Exception as e:
        print(f"App import hatasi: {e}", file=sys.stderr)
        # ML olmadan import edebilmek icin manuel yedek
        raise

    schema = app.openapi()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)
    print(f"OpenAPI JSON yazildi: {OUT_PATH}")
    print(f"   {len(schema.get('paths', {}))} path, "
          f"{len(schema.get('components', {}).get('schemas', {}))} schema")


if __name__ == "__main__":
    main()
