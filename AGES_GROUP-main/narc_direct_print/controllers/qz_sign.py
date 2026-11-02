import base64
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

_QZ_DIR = Path(__file__).resolve().parent.parent / "data" / "qz"
_CERT_PATH = _QZ_DIR / "digital-certificate.txt"
_KEY_PATH = _QZ_DIR / "private-key.pem"


def certificate_pem():
    return _CERT_PATH.read_text(encoding="utf-8")


def sign_request(to_sign):
    """Return a Base64 SHA512/PKCS1 signature for a QZ Tray request."""
    if not to_sign:
        raise ValueError("Nothing to sign.")
    key = serialization.load_pem_private_key(_KEY_PATH.read_bytes(), password=None)
    payload = to_sign.encode("utf-8") if isinstance(to_sign, str) else to_sign
    signature = key.sign(payload, padding.PKCS1v15(), hashes.SHA512())
    return base64.b64encode(signature).decode()
