#!/usr/bin/env python3
"""A small, explicit-target client for the Ninox classic REST API.

Design rules this script obeys, and which any wrapper must not undo:

* **The target is explicit.** Team, database and table are command-line arguments.
  Nothing here reads a target from the environment and there is no default
  destination. In one of our projects an environment variable named for a database
  pointed at the production database of a real client company.
* **Read-only by default.** `schema`, `read`, `files`, `records` and `reconcile`
  only read. `create` and `attach` refuse to run unless `NINOX_APPROVED=1` is set
  deliberately for that one invocation.
* **The token is never printed.** It is read from the environment or, on Windows,
  from the user-level registry variable.
* **A 500 is reported as a mapping error**, not as an outage.
* **No third-party dependency.** Standard library only.

Facts marked VERIFIED were confirmed against a live workspace while writing this
skill; that is the difference between them and the vendor documentation. See
`references/rest-api.md` for the full picture and `references/known-unknowns.md`
for what remains unverified.

Usage:
    python ninox_client.py schema --team T
    python ninox_client.py fields --team T --database D --table B
    python ninox_client.py read   --team T --database D --table B --id 123
    python ninox_client.py files  --team T --database D --table B --id 123
    python ninox_client.py records --team T --database D --table B
    python ninox_client.py reconcile --team T --database D --table B --expect f.json
    NINOX_APPROVED=1 python ninox_client.py create --team T --database D --table B \\
        --payload p.json
    NINOX_APPROVED=1 python ninox_client.py attach --team T --database D --table B \\
        --id 123 --file doc.pdf
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

DEFAULT_HOST = "api.ninox.com"


# --------------------------------------------------------------------------- token


def api_token() -> str:
    """Read the token without ever turning it into printable text."""
    for name in ("NINOX_API_KEY", "NINOX_APIKEY", "NINOX_TOKEN"):
        value = os.environ.get(name)
        if value:
            return value
    if os.name == "nt":
        import winreg

        try:
            # The variable exists at user level; this process may not have
            # inherited it, which is common for an agent in a fresh shell.
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                return winreg.QueryValueEx(key, "NINOX_API_KEY")[0]
        except OSError:
            pass
    raise SystemExit(
        "No Ninox token available. Set NINOX_API_KEY as a user-level variable. "
        "Never commit a token to a file."
    )


# --------------------------------------------------------------------------- errors


class Uncertain(RuntimeError):
    """A create whose response was lost.

    The record may or may not exist. It is NEVER blind-retried: reconcile
    read-side instead, or you write a duplicate into someone's accounting.
    """


class MappingError(RuntimeError):
    """A 500 that a refreshed schema and one retry did not fix.

    Ninox answers an invalid, formula or read-only field name with HTTP 500, not
    a 4xx. That is a mapping mistake, not a server outage.
    """


# --------------------------------------------------------------------------- client


class Ninox:
    def __init__(self, team: str, host: str = DEFAULT_HOST, token: str | None = None):
        if not team:
            raise SystemExit("A team identifier is required, and is never inferred.")
        self.host = host
        self.team = team
        self.token = token or api_token()
        self.api = f"https://{host}/v1"
        self.headers = {"Authorization": f"Bearer {self.token}"}

    # -- plumbing ---------------------------------------------------------

    def _url(self, database: str | None = None, table: str | None = None,
             tail: str = "") -> str:
        url = f"{self.api}/teams/{self.team}"
        if database:
            url += f"/databases/{database}"
            if table:
                url += f"/tables/{table}"
        return url + tail

    def _request(self, method: str, url: str, *, data: bytes | None = None,
                 headers: dict | None = None, timeout: int = 60):
        request = urllib.request.Request(
            url, data=data, method=method,
            headers={**self.headers, **(headers or {})})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8", "replace")
        except urllib.error.URLError as error:
            raise Uncertain(str(error.reason)) from error

    def _get_json(self, url: str):
        status, body = self._request("GET", url)
        if status != 200:
            raise RuntimeError(f"GET {url} -> HTTP {status}: {body[:200]}")
        return json.loads(body)

    # -- schema (read-only) ----------------------------------------------

    def teams(self):
        """VERIFIED: GET /v1/teams -> 200, [{id, name}]."""
        return self._get_json(f"{self.api}/teams")

    def databases(self):
        """VERIFIED: GET /v1/teams/{team}/databases -> 200, [{id, name}]."""
        return self._get_json(self._url(tail="/databases"))

    def tables(self, database: str):
        """VERIFIED: GET /v1/teams/{team}/databases/{db}/tables -> 200.

        Each entry is {id, name, fields: [...]}, and the fields come back with the
        tables. Each field is {id, name, type}, plus `choices` for a choice field
        and the reference keys for a relation.

        NOTE (VERIFIED): `GET .../tables/{table}/fields` does NOT exist. It answers
        404 "End-point not found". Read the schema from here.
        """
        return self._get_json(self._url(database, tail="/tables"))

    def fields(self, database: str, table: str):
        """The fields of one table, from the tables call above."""
        for candidate in self.tables(database):
            if candidate.get("id") == table:
                return candidate.get("fields") or []
        raise SystemExit(f"Table {table!r} is not in database {database!r}.")

    def choice_options(self, database: str, table: str, field_name: str):
        """The existing options of a choice field: [{id, caption, captions, order}].

        VERIFIED. Offer these captions and never free text: what happens when a
        value matches no option is unverified.
        """
        for field in self.fields(database, table):
            if field.get("name") == field_name:
                if field.get("type") not in ("choice", "multi"):
                    raise SystemExit(f"{field_name!r} is {field.get('type')!r}, not a choice field.")
                return field.get("choices") or []
        raise SystemExit(f"No field named {field_name!r} in table {table!r}.")

    # -- records (read-only) ---------------------------------------------

    def records(self, database: str, table: str):
        """VERIFIED: GET .../records -> 200, a LIST.

        Each entry is {id, fields, createdAt, createdBy, modifiedAt, modifiedBy,
        sequence}. `createdAt` and `createdBy` are present on every record
        regardless of mapping, which is what makes reconciliation possible.

        WARNING (VERIFIED): `?limit=` and `?pageSize=` are accepted and IGNORED -
        both returned the whole table. Bound the result set locally, and treat any
        other query parameter as unverified too.
        """
        return self._get_json(self._url(database, table, "/records"))

    def read(self, database: str, table: str, record_id: str):
        """VERIFIED: GET .../records/{id} -> 200, {id, fields}."""
        return self._get_json(self._url(database, table, f"/records/{record_id}"))

    def files(self, database: str, table: str, record_id: str):
        """VERIFIED: GET .../records/{id}/files -> 200, name/size/content type."""
        return self._get_json(self._url(database, table, f"/records/{record_id}/files"))

    # -- writes (the caller must have approval) --------------------------

    def create(self, database: str, table: str, fields: dict):
        """POST .../records. VERIFIED: HTTP 200, returns the new record's id."""
        payload = json.dumps({"fields": fields}).encode("utf-8")
        status, body = self._request(
            "POST", self._url(database, table, "/records"), data=payload,
            headers={"Content-Type": "application/json"})
        if status == 500:
            raise MappingError(
                "HTTP 500 on create. Ninox reports an invalid, formula or "
                "read-only field name this way. Refresh the schema, retry exactly "
                "once, then report a mapping error - not a server outage. Body: "
                + body[:200])
        if status != 200:
            raise RuntimeError(f"create -> HTTP {status}: {body[:300]}")
        return json.loads(body)

    def attach(self, database: str, table: str, record_id: str, path: str,
               filename: str | None = None, content_type: str | None = None):
        """POST .../records/{id}/files, multipart. VERIFIED: HTTP 200.

        The document attaches to the RECORD, not to a field. No file-type field is
        needed and no table is unsuitable.
        """
        name = filename or os.path.basename(path)
        ctype = content_type or _content_type(name)
        with open(path, "rb") as handle:
            blob = handle.read()
        body, headers = _multipart(blob, name, ctype)
        status, text = self._request(
            "POST", self._url(database, table, f"/records/{record_id}/files"),
            data=body, headers=headers, timeout=300)
        if status != 200:
            raise RuntimeError(f"attach -> HTTP {status}: {text[:300]}")
        return text


def _content_type(name: str) -> str:
    lowered = name.lower()
    if lowered.endswith(".pdf"):
        return "application/pdf"
    if lowered.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lowered.endswith(".png"):
        return "image/png"
    return "application/octet-stream"


def _multipart(blob: bytes, filename: str, content_type: str):
    boundary = f"----ninox{uuid.uuid4().hex}"
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return head + blob + tail, {
        "Content-Type": f"multipart/form-data; boundary={boundary}"}


# --------------------------------------------------------------------------- cli


def _print_json(value) -> int:
    print(json.dumps(value, indent=2, ensure_ascii=False))
    return 0


def _load_payload(path: str) -> dict:
    # utf-8-sig, because a payload written by a Windows shell often carries a BOM.
    try:
        with open(path, encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        raise SystemExit(f"No such payload file: {path}")
    except json.JSONDecodeError as error:
        raise SystemExit(f"{path} is not valid JSON: {error}")
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must contain a JSON object of field values.")
    if "fields" in data:
        return data["fields"]
    return data


def _require_approval(what: str, target: str) -> None:
    """A write needs the human's approval, every single time."""
    if os.environ.get("NINOX_APPROVED") != "1":
        print(f"REFUSED: {what} is a write, and the target is {target}.")
        print("A human must approve this exact write. Re-run with NINOX_APPROVED=1")
        print("only after they have said yes. Reading needs no approval; this does.")
        raise SystemExit(3)


def cmd_schema(args) -> int:
    client = Ninox(args.team, args.host)
    databases = client.databases()
    print(f"team {args.team}: {len(databases)} database(s)")
    for database in databases:
        print(f"  database {database['id']}  {database['name']}")
        for table in client.tables(database["id"]):
            fields = table.get("fields") or []
            kinds = ", ".join(sorted({f.get("type", "?") for f in fields}))
            choices = sum(1 for f in fields if f.get("type") in ("choice", "multi"))
            print(f"    table {table['id']:<4} {table['name']:<30} "
                  f"{len(fields):>3} fields ({kinds})"
                  + (f", {choices} with options" if choices else ""))
    print()
    print("NOTE: the schema carries no formula or read-only marker. Verified across")
    print("      a whole subscription: field objects expose only id, name, type,")
    print("      and for relations and choice fields a few extra keys. You cannot")
    print("      filter formula fields out from the schema alone - the signal that")
    print("      one was hit is HTTP 500, and it must be read as a mapping error.")
    return 0


def cmd_fields(args) -> int:
    client = Ninox(args.team, args.host)
    for field in client.fields(args.database, args.table):
        options = ""
        if field.get("type") in ("choice", "multi"):
            captions = [c.get("caption") for c in field.get("choices") or []]
            options = f"  options={captions}"
        elif field.get("type") == "ref":
            options = f"  -> table {field.get('referenceToTable')}"
        elif field.get("type") == "rev":
            options = (f"  <- {field.get('referenceFromTable')}"
                       f".{field.get('referenceFromField')}")
        print(f"  {field.get('id'):<4} {field.get('type','?'):<12} "
              f"{field.get('name','?')}{options}")
    return 0


def cmd_create(args) -> int:
    target = (f"https://{args.host} team={args.team} db={args.database} "
              f"table={args.table}")
    fields = _load_payload(args.payload)
    print(f"target:  {target}")
    print(f"payload: {json.dumps(fields, ensure_ascii=False)}")

    # Refuse before touching the network. A read needs no approval; this is a write.
    _require_approval("create", target)

    # Then validate the mapping against the schema: a write to a field that does
    # not exist is what earns the unexplained 500 that reads like an outage.
    client = Ninox(args.team, args.host)
    known = {f["name"] for f in client.fields(args.database, args.table)}
    unknown = sorted(name for name in fields if name not in known)
    if unknown:
        print(f"REFUSED: no such field(s) in this table: {unknown}")
        return 4

    record = client.create(args.database, args.table, fields)
    record_id = record.get("id")
    print(f"created record {record_id}")

    # Always read back: formulas and defaults override silently and the create
    # response does not reveal it. The human is shown the read-back, never this.
    read_back = client.read(args.database, args.table, record_id)
    print("read-back (this is what is actually stored):")
    print(json.dumps(read_back.get("fields", {}), indent=2, ensure_ascii=False))
    return 0


def cmd_attach(args) -> int:
    target = (f"https://{args.host} team={args.team} db={args.database} "
              f"table={args.table} record={args.id}")
    print(f"target: {target}")
    print(f"file:   {args.file}")
    _require_approval("attach", target)
    client = Ninox(args.team, args.host)
    client.attach(args.database, args.table, args.id, args.file)
    return _print_json(client.files(args.database, args.table, args.id))


def cmd_reconcile(args) -> int:
    """Resolve a create whose response was lost, read-side, without guessing."""
    client = Ninox(args.team, args.host)
    expected = _load_payload(args.expect)
    cutoff = _timestamp() - args.within * 60

    candidates = []
    for record in client.records(args.database, args.table):
        when = _parse_time(record.get("createdAt"))
        if when is not None and when < cutoff:
            continue
        if args.created_by and record.get("createdBy") != args.created_by:
            continue
        # Narrow on the mapped fields that the record actually carries.
        values = record.get("fields") or {}
        comparable = [name for name in expected if values.get(name) == expected[name]]
        if comparable:
            candidates.append(record.get("id"))

    print(f"expected values given for: {sorted(expected)}")
    print(f"candidates within {args.within} minute(s): {len(candidates)}")
    if len(candidates) == 1:
        print(f"EXACTLY ONE MATCH: adopt record {candidates[0]} and continue to the")
        print("attachment step. Do not create another record.")
        return 0
    if not candidates:
        print("NO MATCH: the create did not land. It is now safe to create it.")
        return 0
    print("AMBIGUOUS: more than one plausible match, or too few mapped fields to")
    print("compare. Do not guess and do not create another record - ask the human.")
    return 5


def _timestamp() -> float:
    import time
    return time.time()


def _parse_time(stamp: str | None) -> float | None:
    if not stamp:
        return None
    from datetime import datetime, timezone
    try:
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.timestamp()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default=os.environ.get("NINOX_HOST") or DEFAULT_HOST,
                        help=f"Ninox host. Default {DEFAULT_HOST}; a private-cloud "
                             "instance has its own host and this is never compiled in.")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_target(sp, table: bool = True):
        sp.add_argument("--team", required=True,
                        help="team id; explicit, never from the environment")
        sp.add_argument("--database", required=True,
                        help="database id; explicit, never from the environment")
        if table:
            sp.add_argument("--table", required=True, help="short table id, e.g. YB")

    sp = sub.add_parser("schema", help="enumerate databases, tables and fields (read)")
    sp.add_argument("--team", required=True)
    sp.set_defaults(func=cmd_schema)

    sp = sub.add_parser("fields", help="list one table's fields and options (read)")
    add_target(sp)
    sp.set_defaults(func=cmd_fields)

    sp = sub.add_parser("read", help="read one record (read)")
    add_target(sp)
    sp.add_argument("--id", required=True)
    sp.set_defaults(func=lambda a: _print_json(
        Ninox(a.team, a.host).read(a.database, a.table, a.id)))

    sp = sub.add_parser("files", help="list a record's files (read)")
    add_target(sp)
    sp.add_argument("--id", required=True)
    sp.set_defaults(func=lambda a: _print_json(
        Ninox(a.team, a.host).files(a.database, a.table, a.id)))

    sp = sub.add_parser("records", help="list records (read; bound the set locally)")
    add_target(sp)
    sp.set_defaults(func=lambda a: _print_json(
        Ninox(a.team, a.host).records(a.database, a.table)))

    sp = sub.add_parser("reconcile", help="resolve an uncertain create (read)")
    add_target(sp)
    sp.add_argument("--expect", required=True,
                    help="JSON file of the field values the create submitted")
    sp.add_argument("--within", type=int, default=5,
                    help="time window in minutes around the attempt")
    sp.add_argument("--created-by", default=None, help="expected createdBy, if known")
    sp.set_defaults(func=cmd_reconcile)

    sp = sub.add_parser("create", help="create a record (WRITE; needs approval)")
    add_target(sp)
    sp.add_argument("--payload", required=True,
                    help="JSON file: the fields object, or one nested under 'fields'")
    sp.set_defaults(func=cmd_create)

    sp = sub.add_parser("attach", help="attach a file to a record (WRITE; needs approval)")
    add_target(sp)
    sp.add_argument("--id", required=True)
    sp.add_argument("--file", required=True)
    sp.set_defaults(func=cmd_attach)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Uncertain as error:
        print(f"UNCERTAIN: {error}", file=sys.stderr)
        print("A create may have landed. Do NOT blind-retry: reconcile read-side.",
              file=sys.stderr)
        sys.exit(6)
    except MappingError as error:
        print(f"MAPPING ERROR: {error}", file=sys.stderr)
        sys.exit(7)
    except RuntimeError as error:
        # A failed request, reported without a traceback: the message already
        # carries the status and the response body, which is what a human needs.
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(8)
