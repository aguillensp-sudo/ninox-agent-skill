# Ninox agent skill

An [Agent Skill](https://docs.claude.com/en/docs/claude-code/skills) for AI agents and
scripts that work with the **Ninox** low-code database platform.

It is not a summary of the vendor's marketing pages. It is a working contract, and it
exists because the intuitive implementation of a Ninox client is wrong in at least four
specific places — each of which cost us real time to discover.

## The four that bite

1. **An HTTP 500 from this API usually means *your* field mapping is wrong.** Ninox
   reports an invalid, formula or read-only field name as `500`, not as a `4xx` with an
   explanation. A client that reads `500` as "server unwell" and retries forever hammers
   the API over its own mistake.
2. **The schema does not mark formula or read-only fields.** Verified across 8,048
   fields in 566 tables: a field object carries only `id`, `name` and `type`. You cannot
   filter formula fields out by reading the schema — the only reliable filter is a human
   mapping decision.
3. **A create must always be read back.** Fields carrying formulas or defaults silently
   override what you submitted, and the create response does not reveal it.
4. **Never blind-retry a create whose response was lost.** It may have landed. Retrying
   writes a duplicate into someone's accounting; the answer is read-side reconciliation.

## What is in here

```
SKILL.md                              the entry point: rules, workflow, when to read what
references/rest-api.md                endpoints, shapes, status codes, verified vs documented
references/schema-and-fields.md       the model, identifiers vs names, field types, the formula trap
references/write-path.md              create → attach → read-back, mapping rules, conventions
references/errors-and-retries.md      the retry matrix and reconciliation of an uncertain create
references/credentials-and-safety.md  token handling, explicit targeting, the production-database trap
references/known-unknowns.md          what is genuinely unverified — read before claiming a limit
scripts/check_credentials.py          check a token by length and effect, never by value
scripts/ninox_client.py               explicit-target client; read-only by default
```

## Install

Copy or symlink the whole directory into your agent's skills directory. For Claude
Code that is `~/.claude/skills/ninox/`; other harnesses that implement the Agent Skills
format use an equivalent path.

```bash
git clone https://github.com/nortexsys/ninox-agent-skill.git
cp -r ninox-agent-skill ~/.claude/skills/ninox
```

The scripts need Python 3.10 or later and **no packages** — standard library only.

## Use the scripts

```bash
# check the credential without ever printing it, then prove it works by its effect
python scripts/check_credentials.py
python scripts/check_credentials.py --verify

# read a schema (safe, no approval needed)
python scripts/ninox_client.py schema --team <TEAM_ID>
python scripts/ninox_client.py fields --team <TEAM_ID> --database <DB_ID> --table YB

# read a record, and its attachments
python scripts/ninox_client.py read  --team T --database D --table YB --id 123
python scripts/ninox_client.py files --team T --database D --table YB --id 123

# a write needs a human's approval, explicitly, for that one invocation
NINOX_APPROVED=1 python scripts/ninox_client.py create \
    --team T --database D --table YB --payload payload.json
```

The token is read from `NINOX_API_KEY` in the environment, or on Windows from the
user-level registry variable, and is never printed.

**The target is always explicit.** The scripts refuse to take a team, database or
table from the environment, and there is no default destination. That is deliberate —
see below.

## Why the safety rules are this strict

In one of our projects the environment carried a variable named for a database, and in
that environment it pointed at the **production database of a real client company**. A
script that let the environment choose its target would have written test records into
a live system. Nothing bad happened because the target was passed explicitly. That is
the rule, and it was not luck.

The same discipline applies to credentials: a token is never printed, never logged,
never written into a document. It is checked by its **length** or its **effect**.

## Provenance

The behavioural rules here come from Nortex Systems' Ninox work:

- a full request-and-response trace of the classic write API, taken during an earlier
  automation project; and
- an end-to-end test that created, uploaded to, read back and inspected **sixteen real
  documents** against a disposable table, all uploads answering HTTP 200.

The endpoint and schema facts marked **VERIFIED** in `references/rest-api.md` were
confirmed against a live workspace while this skill was written, and the numbers quoted
(8,048 fields, 566 tables, the `type` vocabulary, `?limit` and `?pageSize` being
ignored) are measurements from that pass, not recollections.

Where something is **not** established — a maximum upload size, real upload timings, the
behaviour of a choice field written with text matching none of its options — it is
listed in `references/known-unknowns.md` rather than replaced with a plausible number.

## Privacy

This repository contains no customer data and no customer identifiers. Team, database,
table and record identifiers appear as placeholders only. The scripts read their target
from the command line and their token from the environment; neither is stored here.

When contributing, do not add a real schema dump, a record read-back, a log, or OCR
output. A keyword search does not see inside binary documents — text in a `.docx` lives
in `word/document.xml` — so check binaries explicitly rather than trusting a text grep.

## Contributing

Corrections that come with evidence are the most welcome kind. If you close one of the
open questions in `references/known-unknowns.md`, record the exact request, the exact
response and the date, and update that file — a gap closed in a test and left open here
will be re-discovered by error.

## Licence

MIT. See `LICENSE`.
