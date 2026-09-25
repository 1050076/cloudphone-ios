#!/usr/bin/env python
"""Create (idempotently) the App ID + App Store provisioning profile this app is
signed with, straight from the App Store Connect API -- no Mac, no portal.

Why: xcodebuild's automatic signing fails on a CI runner
(`Authentication failed: Make sure a bearer token was provided` at
GatherProvisioningInputs) even though the very same API key builds certificates
and profiles fine over REST. The workflow therefore signs manually and needs a
profile that already exists; this script is where it comes from.

Run it again whenever the profile expires or the App ID's capabilities change
(a profile is a snapshot of the capabilities at creation time).

  python scripts/make-ios-signing-assets.py \
      --bundle-id com.example.app --app-id-name CloudPhone \
      --profile-name "CloudPhone App Store" --out-dir ~/.config/cloudphone-secrets

Env: ASC_KEY_ID / ASC_ISSUER_ID / ASC_KEY_PATH (see scripts/asc_api.py).
Needs `cryptography`; on this machine that means
"C:/Program Files/Python/Python311/python.exe".
"""
import argparse
import base64
import pathlib
import plistlib
import re
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import asc_api  # noqa: E402


def find_bundle_id(identifier: str):
    query = urllib.parse.urlencode({"filter[identifier]": identifier, "limit": 10})
    data = asc_api.call("GET", f"/bundleIds?{query}")
    for item in data.get("data", []):
        if item["attributes"]["identifier"] == identifier:
            return item
    return None


def ensure_bundle_id(identifier: str, name: str):
    existing = find_bundle_id(identifier)
    if existing:
        print(f"✓ App ID exists: {identifier} ({existing['id']})")
        return existing["id"]
    body = {
        "data": {
            "type": "bundleIds",
            "attributes": {"identifier": identifier, "name": name, "platform": "IOS"},
        }
    }
    created = asc_api.call("POST", "/bundleIds", body)["data"]
    print(f"✓ App ID created: {identifier} ({created['id']})")
    return created["id"]


def distribution_certificate():
    """The distribution certificate the p12 in the workflow secrets belongs to."""
    data = asc_api.call(
        "GET",
        "/certificates?filter[certificateType]=IOS_DISTRIBUTION,DISTRIBUTION&limit=50",
    )
    certs = data.get("data", [])
    if not certs:
        raise SystemExit("no distribution certificate in this team; create one first")
    cert = max(certs, key=lambda c: c["attributes"].get("expirationDate", ""))
    attribute = cert["attributes"]
    print(
        f"✓ certificate: {cert['id']} {attribute.get('displayName')} "
        f"expires {attribute.get('expirationDate')}"
    )
    return cert["id"]


def ensure_profile(name: str, bundle_id: str, certificate_id: str):
    # Profile names contain spaces: percent-encode or urllib refuses the URL.
    query = urllib.parse.urlencode({"filter[name]": name, "limit": 20})
    data = asc_api.call("GET", f"/profiles?{query}")
    for item in data.get("data", []):
        if item["attributes"]["name"] != name:
            continue
        if item["attributes"]["profileState"] == "ACTIVE":
            print(f"✓ profile exists: {name} ({item['id']})")
            return item["id"]
        # INVALID profiles (App ID capabilities changed) block recreating the
        # same name, so drop them first.
        asc_api.call("DELETE", f"/profiles/{item['id']}")
        print(f"▸ dropped invalid profile {name} ({item['id']})")

    body = {
        "data": {
            "type": "profiles",
            "attributes": {"name": name, "profileType": "IOS_APP_STORE"},
            "relationships": {
                "bundleId": {"data": {"type": "bundleIds", "id": bundle_id}},
                "certificates": {"data": [{"type": "certificates", "id": certificate_id}]},
            },
        }
    }
    created = asc_api.call("POST", "/profiles", body)["data"]
    print(f"✓ profile created: {name} ({created['id']})")
    return created["id"]


def verify(profile_content_b64: str, expected_bundle_id: str) -> dict:
    """Fail here rather than 40 minutes later inside xcodebuild."""
    raw = base64.b64decode(profile_content_b64)
    match = re.search(rb"<\?xml.*?</plist>", raw, re.S)
    if not match:
        raise SystemExit("profile has no embedded plist")
    plist = plistlib.loads(match.group(0))
    entitlements = plist.get("Entitlements", {})
    identifier = entitlements.get("application-identifier", "")
    checks = {
        "bundle id": identifier.endswith("." + expected_bundle_id),
        "beta-reports-active (required to upload TestFlight builds)": entitlements.get(
            "beta-reports-active"
        )
        is True,
        "not a development profile": entitlements.get("get-task-allow") is False,
        "distribution certificate (not Xcode managed)": not plist.get("IsXcodeManaged"),
    }
    for label, ok in checks.items():
        print(f"  {'✓' if ok else '✗'} {label}")
    for label, ok in checks.items():
        if not ok:
            raise SystemExit(f"profile failed precheck: {label}")
    return plist


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--app-id-name", required=True, help="name of the App ID, not the app")
    parser.add_argument("--profile-name", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    out_dir = pathlib.Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    bundle = ensure_bundle_id(args.bundle_id, args.app_id_name)
    certificate = distribution_certificate()
    profile_id = ensure_profile(args.profile_name, bundle, certificate)

    data = asc_api.call("GET", f"/profiles/{profile_id}")["data"]
    content = data["attributes"]["profileContent"]
    if not content:
        raise SystemExit("profile has no content")

    plist = verify(content, args.bundle_id)

    profile_path = out_dir / "app.mobileprovision"
    b64_path = out_dir / "app.profile.b64"
    profile_path.write_bytes(base64.b64decode(content))
    b64_path.write_text(content)
    for path in (profile_path, b64_path):
        if path.stat().st_size == 0:
            raise SystemExit(f"{path} is empty -- refusing to hand it to gh secret set")
    print(f"✓ {profile_path} ({profile_path.stat().st_size} bytes)")
    print(f"✓ {b64_path} ({b64_path.stat().st_size} bytes)")
    print(f"  profile name  : {plist.get('Name')}")
    print(f"  uuid          : {plist.get('UUID')}")
    print(f"  expires       : {plist.get('ExpirationDate')}")


if __name__ == "__main__":
    main()
