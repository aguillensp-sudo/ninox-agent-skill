# Credentials and safety

Two of the rules here exist because of a specific near-miss, which is recorded so
that a later reader does not treat the rules as excessive caution.

## The token is the only credential

- The credential is a **personal access token**, sent as
  `Authorization: Bearer <token>`.
- **Never** ask for, store or transmit a Ninox username or password. Where a real
  product is being built, the token is obtained through the platform's own system
  browser, never an app-controlled WebView, and it lives in the platform keystore or
  keychain — not in the destination record and not in a configuration export.
- A token is scoped to the **user**, so it can see everything that user can see. It
  is not scoped to the database you happen to be working on. Treat it accordingly.

## Never print the value

A token that reaches a log, a transcript, a commit or an issue is compromised.

- Never print it, never `echo` it, never pass it as a command-line argument (it lands
  in the process list and the shell history), never write it to a document.
- **Check a credential by its length or its effect, never its value.** "Present, 64
  characters" is a usable diagnostic; the value is not.
- A useful effect-check is a cheap authenticated read — enumerating teams, or reading
  the schema of the table you care about. If that succeeds, the token works. That is
  a real verification, and it leaks nothing.
- Mask anything derived from it. If you must show a fingerprint, show its shape with
  the alphanumerics replaced, not a prefix.

## Never let the environment choose the target

**This is the rule with the near-miss behind it.**

In one of our projects the environment carried a `NINOX_DB_ID` variable, and in that
environment it pointed at the **production database of a real client company**. Any
script that read its target from the environment and was run from that shell would
have written test records into a live ERP. Nothing bad happened, because the target
was passed explicitly — that is the rule, and it was not luck.

Therefore:

- **The target is always explicit**: team, database and table are stated by the caller
  or by the user's stored destination. Never inferred, never defaulted from the
  environment.
- A **destination** is the tuple of Ninox host, team, database, table and field
  mapping. Several destinations coexist; nothing is global.
- Do not provide a built-in default destination. Before the user has configured one,
  there is nothing to write to, and that is the correct state.
- When a script needs a target and none was given, it **fails** and says so. It does
  not guess, and it does not fall back to "whatever the environment says".

## Read the token without ever handling its text carelessly

On Windows the token may exist as a **user-level environment variable** in the
registry rather than in the process environment, because the shell the agent runs in
may not have inherited it. Read it programmatically:

```python
import os

def api_token() -> str:
    token = os.environ.get("NINOX_API_KEY")
    if token:
        return token
    # The variable exists at user level; this process may not have inherited it.
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            return winreg.QueryValueEx(key, "NINOX_API_KEY")[0]
    except OSError:
        pass
    raise SystemExit("NINOX_API_KEY is not available")
```

Never fall back to a token committed in a file, and never prompt for one by echoing
what was typed.

## Approval discipline

- **Reading is not writing.** Enumerating teams, reading a schema and reading a record
  are safe and expected. Creating, updating, attaching and deleting are not.
- **Never write to Ninox without the human's explicit approval** — not even to a test
  base, and not even to clean up after yourself. Deleting a record you created in
  error is still a write; ask.
- Before a write, state plainly: the host, the team, the database, the table, and the
  fields the payload will target. Then wait.
- Prefer read-only credentials for exploration. If the token can write, the script
  still must not.

## Data leaving the device

- Where the data came from a person's documents, the destination is the user's own
  Ninox workspace and nowhere else. No intermediate backend, no third-party service,
  no telemetry carrying document content.
- Where you are debugging, quote field **names** and **shapes**, not field values.
  A record read-back pasted into a transcript can carry a real person's name, tax
  identifier, plate or card digits.
- Watch for identifiers that *are* the identification: removing a person's name while
  keeping their tax identifier or registration plate does not anonymise anything.
- When publishing code or documentation, remember that a keyword search does not see
  inside binary documents. Text in `.docx` lives in `word/document.xml`, and OCR
  output, logs and SQL dumps are the usual places real data leaks from. Exclude them
  from the repository and verify the exclusion path by path rather than trusting the
  pattern.
