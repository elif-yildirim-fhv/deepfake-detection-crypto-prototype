import hashlib
import io
from typing import Optional

import imagehash
from PIL import Image


def compute_sha256(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def compute_phash(file_bytes: bytes) -> Optional[str]:
    try:
        img = Image.open(io.BytesIO(file_bytes))
        return str(imagehash.phash(img))
    except Exception:
        return None


def verify_integrity(file_bytes: bytes, expected_hash: str) -> bool:
    return compute_sha256(file_bytes) == expected_hash.lower().strip()
