import hashlib


def compute_sha256(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def verify_integrity(file_bytes: bytes, expected_hash: str) -> bool:
    return compute_sha256(file_bytes) == expected_hash.lower().strip()
