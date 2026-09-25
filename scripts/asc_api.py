#!/usr/bin/env python
"""Minimal App Store Connect API client (ES256 JWT + thin REST wrappers).

Why it exists: portal state (build processing/review state, TestFlight group
membership, review contact info) has to be verifiable from the command line,
and driving the web UI for it means a human login every time the cookie dies.

Config (env, else inferred):
  ASC_KEY_ID     team key id, e.g. ABCD123456
  ASC_ISSUER_ID  issuer uuid from the ASC API page
  ASC_KEY_PATH   path to AuthKey_<KEY_ID>.p8
                 default: first ~/.config/*-secrets/AuthKey_*.p8 found

Usage:
  asc_api.py whoami                 # prints team id(s) from /bundleIds seedId
  asc_api.py get   /builds?filter[app]=<appId>&sort=-uploadedDate
  asc_api.py post  /betaAppReviewSubmissions body.json
  asc_api.py patch /betaAppReviewDetails/<appId> body.json

Notes that cost time:
  * JWS ES256 wants the RAW 32-byte r||s pair. `private_key.sign()` returns a
    DER SEQUENCE -- decode it with utils.decode_dss_signature and re-pack, or
    every request comes back 401 with no hint about the signature format.
  * `GET /v1/bundleIds` -> attributes.seedId is the Team ID; no portal digging.
  * Relationship POSTs (assign a build to a beta group) succeed with an empty
    body `{}` -- that is success, not a failure.
  * Needs the `cryptography` package: use a real CPython (3.11+), not a
    stripped embeddable runtime. On this machine:
    "C:/Program Files/Python/Python311/python.exe".
"""
import base64
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

API = "https://api.appstoreconnect.apple.com/v1"


def find_key_path() -> pathlib.Path:
    explicit = os.environ.get("ASC_KEY_PATH")
    if explicit:
        return pathlib.Path(explicit).expanduser()
    roots = [pathlib.Path.home() / ".config"]
    for root in roots:
        if not root.is_dir():
            continue
        for candidate in sorted(root.glob("*-secrets/AuthKey_*.p8") + root.glob("AuthKey_*.p8")):
            return candidate
    raise SystemExit("no AuthKey_*.p8 found; set ASC_KEY_PATH")


def key_id_from(path: pathlib.Path) -> str:
    return os.environ.get("ASC_KEY_ID") or path.stem.replace("AuthKey_", "")


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def token() -> str:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, utils

    key_path = find_key_path()
    issuer = os.environ.get("ASC_ISSUER_ID")
    if not issuer:
        raise SystemExit("set ASC_ISSUER_ID (ASC -> Users and Access -> Integrations)")

    now = int(time.time())
    header = {"alg": "ES256", "kid": key_id_from(key_path), "typ": "JWT"}
    payload = {"iss": issuer, "iat": now, "exp": now + 900, "aud": "appstoreconnect-v1"}
    signing_input = f"{b64url(json.dumps(header).encode())}.{b64url(json.dumps(payload).encode())}".encode()

    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    r, s = utils.decode_dss_signature(key.sign(signing_input, ec.ECDSA(hashes.SHA256())))
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return f"{signing_input.decode()}.{b64url(raw)}"


def call(method: str, path: str, body=None):
    request = urllib.request.Request(f"{API}{path}", method=method)
    request.add_header("Authorization", f"Bearer {token()}")
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, data=data, timeout=60) as response:
            raw = response.read().decode() or "{}"
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as error:
        body_text = error.read().decode()
        raise SystemExit(f"HTTP {error.code} {method} {path}\n{body_text[:1500]}")


def main(argv):
    cmd = argv[0] if argv else "whoami"
    if cmd == "get":
        print(json.dumps(call("GET", argv[1]), ensure_ascii=False, indent=1))
    elif cmd in ("post", "patch", "delete"):
        body = json.loads(pathlib.Path(argv[2]).read_text()) if len(argv) > 2 else None
        print(json.dumps(call(cmd.upper(), argv[1], body), ensure_ascii=False, indent=1))
    elif cmd == "whoami":
        data = call("GET", "/bundleIds?limit=200")
        seeds = {b["attributes"].get("seedId") for b in data.get("data", []) if b["attributes"].get("seedId")}
        print("team ids:", ", ".join(sorted(seeds)) or "(none)")
        print("key id:", key_id_from(find_key_path()))
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv[1:])
