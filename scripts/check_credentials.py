#!/usr/bin/env python3
"""Report whether a Ninox token and an explicit target are available.

This script exists so that a credential can be checked *without its value ever
being handled as text that could be printed, logged or committed*. It reports
presence, length and a coarse shape hint, and nothing else.

It also deliberately refuses to treat an environment-provided database as a
target. In one of our projects an environment variable named for a database
pointed at the **production database of a real client company**; a script that
read its target from the environment from that shell would have written into a
live system. The target is always passed explicitly.

Usage:
    python check_credentials.py                    # presence and shape only
    python check_credentials.py --verify --team T  # also prove the token works

`--verify` performs one authenticated read (listing teams). That is a read, and
it is the honest way to check a credential: by its effect, never by its value.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

TOKEN_NAMES = (
    "NINOX_API_KEY",
    "NINOX_APIKEY",
    "NINOX_TOKEN",
    "NINOX_API_TOKEN",
    "NINOX_PAT",
)

# Names that look like a credential but are not, so they are never reported as one.
NOT_A_TOKEN = {
    "NINOX_TEAM_ID",
    "NINOX_DB_ID",
    "NINOX_DATABASE_ID",
    "NINOX_TABLE_ID",
}

DEFAULT_HOST = "api.ninox.com"


def mask_shape(value: str) -> str:
    """A shape with every alphanumeric replaced. Reveals nothing, still useful."""
    return re.sub(r"[A-Za-z0-9]", "#", value)[:60]


def describe(value: str | None) -> str:
    if not value:
        return "ABSENT"
    hint = ""
    if re.fullmatch(r"[0-9a-fA-F]{32}", value):
        hint = " (looks like 32 hex chars)"
    elif re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", value):
        hint = " (looks like a UUID)"
    return f"present, {len(value)} chars{hint}"


def token_from_environment() -> tuple[str | None, str]:
    """Return (token, where it came from), never the token's text in the source."""
    for name in TOKEN_NAMES:
        value = os.environ.get(name)
        if value:
            return value, f"process environment ({name})"

    # A user-level variable exists in the registry, and this process may not
    # have inherited it. This is common when an agent runs in a fresh shell.
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value = winreg.QueryValueEx(key, "NINOX_API_KEY")[0]
            if value:
                return value, "user environment (HKCU\\Environment)"
        except OSError:
            pass

    return None, "not found"


def report_environment_targets() -> None:
    print("== environment targets (informational, and not to be trusted) ==")
    found_any = False
    for name in sorted(n for n in os.environ if "NINOX" in n.upper()):
        if name.upper() in NOT_A_TOKEN or name.upper() in TOKEN_NAMES:
            continue
        found_any = True
        print(f"  {name} is set")
    if found_any:
        print()
        print("  WARNING: a target taken from the environment is exactly how test")
        print("  records can land in a production database. Pass the team, database")
        print("  and table explicitly; never let these variables choose the target.")
    else:
        print("  (none set - which is the good state)")


def verify(host: str, token: str) -> int:
    url = f"https://{host}/v1/teams"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        # An HTTP error is reported by status only; a body can echo request data.
        print(f"  GET /v1/teams -> HTTP {error.code}")
        if error.code in (401, 403):
            print("  the token was rejected: it is absent, expired or revoked")
        return 1
    except urllib.error.URLError as error:
        print(f"  GET /v1/teams -> unreachable ({error.reason})")
        print("  check the host: a private-cloud deployment has its own hostname")
        return 1

    teams = body if isinstance(body, list) else body.get("data", [])
    print(f"  GET /v1/teams -> HTTP 200, {len(teams)} team(s) visible")
    print("  the token works. It is not scoped to one database, so treat it as")
    print("  full access to everything this user can see.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verify", action="store_true",
                        help="perform one authenticated read to prove the token works")
    parser.add_argument("--host", default=os.environ.get("NINOX_HOST") or DEFAULT_HOST,
                        help=f"Ninox host, default {DEFAULT_HOST}")
    args = parser.parse_args()

    print("== token ==")
    token, source = token_from_environment()
    for name in TOKEN_NAMES:
        if os.environ.get(name):
            print(f"  {name:18s} {describe(os.environ[name])}")
    if token:
        print(f"  resolved from: {source}")
        print(f"  shape: {mask_shape(token)}")
    else:
        print("  no Ninox token available")
        print("  set NINOX_API_KEY as a user-level variable, or export it for this shell")

    print()
    print("== host ==")
    print(f"  {args.host} (configuration, default {DEFAULT_HOST}, never a compiled constant)")

    print()
    report_environment_targets()

    if not token:
        return 2

    if args.verify:
        print()
        print("== effect check ==")
        return verify(args.host, token)

    print()
    print("token present. Re-run with --verify to prove it works by its effect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
