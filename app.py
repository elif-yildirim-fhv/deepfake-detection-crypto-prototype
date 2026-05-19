from flask import Flask, request, jsonify, render_template, send_file
import io
import wave
from PIL import Image, ImageDraw
import imagehash
from crypto.hash_utils import compute_sha256
from crypto.signature_utils import (
    generate_key_pair,
    serialize_private_key,
    serialize_public_key,
    load_private_key,
    load_public_key,
    sign_hash,
    verify_signature,
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024


def compute_phash(file_bytes: bytes) -> str:
    try:
        img = Image.open(io.BytesIO(file_bytes))
        return str(imagehash.phash(img))
    except Exception:
        return None

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/generate-keys", methods=["POST"])
def api_generate_keys():
    private_key, public_key = generate_key_pair()
    return jsonify({
        "private_key": serialize_private_key(private_key),
        "public_key": serialize_public_key(public_key),
    })


@app.route("/api/sign", methods=["POST"])
def api_sign():
    file = request.files.get("file")
    private_key_pem = request.form.get("private_key")

    if not file or not private_key_pem:
        return jsonify({"error": "Datei und Private Key erforderlich"}), 400

    file_bytes = file.read()
    sha256_hex = compute_sha256(file_bytes)
    phash_hex = compute_phash(file_bytes)

    try:
        private_key = load_private_key(private_key_pem)
    except Exception:
        return jsonify({"error": "Ungültiger Private Key"}), 400

    signature = sign_hash(private_key, sha256_hex)

    return jsonify({
        "filename": file.filename,
        "sha256": sha256_hex,
        "phash": phash_hex,
        "signature": signature,
    })


@app.route("/api/verify", methods=["POST"])
def api_verify():
    file = request.files.get("file")
    public_key_pem = request.form.get("public_key")
    original_hash = request.form.get("sha256")
    original_phash = request.form.get("phash")
    signature = request.form.get("signature")

    if not file or not public_key_pem or not original_hash or not signature:
        return jsonify({"error": "Alle Felder (außer pHash) sind erforderlich"}), 400

    file_bytes = file.read()
    current_hash = compute_sha256(file_bytes)
    integrity_ok = (current_hash == original_hash.lower().strip())

    current_phash = compute_phash(file_bytes)
    phash_ok = None
    phash_diff = None
    if original_phash and original_phash != "None" and current_phash:
        try:
            h1 = imagehash.hex_to_hash(original_phash)
            h2 = imagehash.hex_to_hash(current_phash)
            phash_diff = h1 - h2
            phash_ok = (phash_diff <= 3)
        except Exception:
            pass

    try:
        public_key = load_public_key(public_key_pem)
        signature_ok = verify_signature(public_key, original_hash, signature)
    except Exception:
        return jsonify({"error": "Ungültiger Public Key oder Signatur"}), 400

    if phash_diff is not None:
        phash_diff = int(phash_diff)
    if phash_ok is not None:
        phash_ok = bool(phash_ok)

    return jsonify({
        "filename": file.filename,
        "original_hash": original_hash,
        "current_hash": current_hash,
        "integrity_ok": integrity_ok,
        "original_phash": original_phash,
        "current_phash": current_phash,
        "phash_ok": phash_ok,
        "phash_diff": phash_diff,
        "signature_ok": signature_ok,
        "tampered": not integrity_ok,
    })


def _tamper_image(file_bytes: bytes, ext: str) -> bytes:
    img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    pixels = img.load()
    r, g, b = pixels[0, 0]
    pixels[0, 0] = (255 - r, g, b)
    out = io.BytesIO()
    fmt = "JPEG" if ext.lower() in ("jpg", "jpeg") else ext.upper()
    img.save(out, format=fmt)
    return out.getvalue()

def _tamper_harmless(file_bytes: bytes, ext: str) -> bytes:
    img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    out = io.BytesIO()
    fmt = "JPEG" if ext.lower() in ("jpg", "jpeg") else ext.upper()
    try:
        img.save(out, format=fmt, quality=30)
    except Exception:
        img.save(out, format=fmt)
    return out.getvalue()

def _tamper_deepfake(file_bytes: bytes, ext: str) -> bytes:
    img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    w, h = img.size
    draw = ImageDraw.Draw(img)
    bw, bh = w * 0.6, h * 0.6
    x0, y0 = (w - bw) / 2, (h - bh) / 2
    draw.rectangle([x0, y0, x0 + bw, y0 + bh], fill="magenta")
    out = io.BytesIO()
    fmt = "JPEG" if ext.lower() in ("jpg", "jpeg") else ext.upper()
    img.save(out, format=fmt)
    return out.getvalue()


def _tamper_audio(file_bytes: bytes) -> bytes:
    buf = io.BytesIO(file_bytes)
    with wave.open(buf, "rb") as w:
        params = w.getparams()
        frames = bytearray(w.readframes(w.getnframes()))

    if len(frames) >= 2:
        frames[0] ^= 0x01

    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setparams(params)
        w.writeframes(bytes(frames))
    return out.getvalue()


def _tamper_generic(file_bytes: bytes) -> bytes:
    data = bytearray(file_bytes)
    pos = max(16, len(data) // 10)
    if pos < len(data):
        data[pos] ^= 0xFF
    else:
        data += b"\x00"
    return bytes(data)


@app.route("/api/tamper", methods=["POST"])
def api_tamper():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "Datei erforderlich"}), 400

    filename = file.filename or "datei"
    file_bytes = file.read()
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    attack_type = request.form.get("attack_type", "pixel")

    method = "Generisch (Byte-Flip)"
    try:
        if ext in ("jpg", "jpeg", "png", "bmp", "gif", "webp"):
            if attack_type == "harmless":
                modified = _tamper_harmless(file_bytes, ext)
                method = "Harmlose Kompression (SHA-256 schlägt an, pHash bleibt gleich)"
            elif attack_type == "deepfake":
                modified = _tamper_deepfake(file_bytes, ext)
                method = "Deepfake-Simulation (Inhalt stark verändert, pHash schlägt an)"
            else:
                modified = _tamper_image(file_bytes, ext)
                method = "Bild-Pixel verändert (simuliert minimale Manipulation)"
        elif ext == "wav":
            modified = _tamper_audio(file_bytes)
            method = "Audio-Sample verändert (simuliert Audio-Deepfake)"
        else:
            modified = _tamper_generic(file_bytes)
            method = "Datei-Byte verändert (simuliert Deepfake-Manipulation)"
    except Exception:
        modified = _tamper_generic(file_bytes)

    buf = io.BytesIO(modified)
    buf.seek(0)

    if "." in filename:
        name, ext_orig = filename.rsplit(".", 1)
        download_name = f"{name}_manipuliert.{ext_orig}"
    else:
        download_name = f"{filename}_manipuliert"

    response = send_file(
        buf,
        as_attachment=True,
        download_name=download_name,
        mimetype="application/octet-stream",
    )
    response.headers["X-Tamper-Method"] = method
    return response


if __name__ == "__main__":
    app.run(debug=True)
