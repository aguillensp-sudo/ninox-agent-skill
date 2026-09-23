---
name: ninox
description: Work with the Ninox low-code database platform from an agent or a script. Covers the classic REST API (teams, databases, tables, records, attachments), the schema and field-mapping model, credential handling, and the write-path failure modes that cost real money. Use when a task involves reading from or writing to a Ninox team, database or table; uploading an attachment to a Ninox record; mapping external data onto Ninox fields; enumerating a Ninox schema; or diagnosing a Ninox API error such as an unexpected HTTP 500.
---

# Working with Ninox

Ninox is a low-code database platform. This skill is for agents and scripts that
talk to it over its **classic REST API**, and it exists because the intuitive
implementation is wrong in at least four specific places.

Read this file before writing any code. Read the reference that matches the task.
Do not read every reference speculatively.

## The rules that are not negotiable

These were each paid for once already. They are stated as rules because the
intuitive answer is wrong for several of them.

1. **An HTTP 500 is usually your mapping, not an outage.** Ninox returns `500` for
   an invalid, formula or read-only field name — not a `4xx` with an explanation.
   A client that reads `500` as "server unwell" and retries forever hammers the API
   over its own mistake and never mentions it. On a `500`: refresh the schema, retry
   **exactly once**, then report a **mapping error** to the human.
2. **Always read a record back after creating it.** Fields carrying formulas or
   defaults silently override what you submitted, and the create response does not
   reveal it. Show the human the read-back, never what you sent.
3. **Never blind-retry a create whose response was lost.** A timed-out `POST` may
   have landed. Retrying it writes a duplicate into someone's accounting. Enter an
   `uncertain` state and **reconcile read-side** instead — see
   `references/errors-and-retries.md`.
4. **Attachments belong to the record, not to a field.** A file-type field is not
   required and no table is unsuitable. See `references/write-path.md`.
5. **Store field identifiers, send field names.** The schema identifies a field by a
   stable identifier; the payload is keyed by its *current name*. Configuration that
   stores names breaks silently the first time a column is renamed.
6. **Never write anything without the human's explicit approval.** Not even to a test
   base. Reading a schema is not writing; creating, updating and attaching are.
   Dry-run first, and show what would be written.
7. **Never let an environment variable choose the target database.** The target is
   passed explicitly. See `references/credentials-and-safety.md` — there is a real
   near-miss behind this rule.
8. **Never print, log or echo the API token.** Check a credential by its length or
   its effect, never its value.
9. **State nothing you have not read in this session.** Not the shape of a table,
   not the state of a record, not the contents of a field. Read it, then assert it.

## Choose the API generation deliberately

Ninox exposes two live interfaces, and picking the wrong one is a design mistake
that is expensive to undo:

| | Classic (classic REST) | Newer (workspace/module) |
| --- | --- | --- |
| Organised as | teams → databases → tables | workspaces → modules |
| Credential | one personal access token | a workspace-scoped key |
| Enumeration | one token walks teams, then databases, then tables with their fields | bound to a single workspace |
| Attachment upload | one `multipart/form-data` call | presigned storage URLs, three steps |
| Base URL | `https://api.ninox.com/v1` | see vendor docs |

**Use the classic interface** when the task needs to enumerate a subscription and
offer the user a choice of database, or when a one-call upload matters. It is what
this skill documents. The vendor describes it as the previous generation, so isolate
the client behind a port (`references/rest-api.md` shows the shape) rather than
letting its URLs spread through the codebase.

**Never compile the host in as a constant.** Ninox is offered as a private cloud on
a customer-specific host, which is common in larger German companies. The host is
configuration, defaulting to `api.ninox.com`, and is validated when the token is
entered rather than deferred to the first write.

## The write path

A send is **three steps, in this order**, and the third one is not optional:

1. **Create** the record — `POST .../records` with the fields nested under a
   `fields` key. A `200` returns the new record's identifier.
2. **Attach** the document — `POST .../records/{id}/files`, `multipart/form-data`.
3. **Read back** — `GET .../records/{id}`, and this read-back is what the human is
   shown.

A send that created a record but failed to attach its document is **incomplete, not
done**: retry the attachment alone. Updates are merges, so a retry that touches only
the attachment changes nothing else.

Details, including payload shape, date and money conventions, and the mapping rules
for formula fields, choice fields and absent values: `references/write-path.md`.

## Failure handling

Do not improvise this at the moment of failure; the classification is
counter-intuitive. The full matrix and the reconciliation algorithm are in
`references/errors-and-retries.md`. The short version:

| Condition | Behaviour |
| --- | --- |
| No connectivity | Queue, send when connectivity returns |
| Timeout / network error on **create** | `uncertain` → reconcile read-side, **never** blind-retry |
| Timeout on attachment or read-back | Bounded exponential backoff (neither can duplicate a record) |
| `401` / `403` | Authentication problem: ask for a new token, **no** retry |
| `404` | The database or table is gone: send the human to the destination, no retry |
| `500` | Refresh schema, retry **once**, then report a **mapping error** |
| Record created, attachment failed | Retry the attachment only |

## Before you write anything

- State the exact team, database and table you are about to write to, explicitly.
- Show the payload you intend to send, and list every field it targets.
- Confirm the human approved **this** write.
- Prefer `--dry-run`, then the real call.

## References

- `references/rest-api.md` — endpoints, payload and response shapes, status codes,
  and the API-generation split. Marks what is vendor-documented separately from what
  our own projects verified.
- `references/schema-and-fields.md` — teams, databases, tables, fields; identifiers
  versus names; field types; formula, read-only and choice fields.
- `references/write-path.md` — create → attach → read-back, mapping rules, payload
  conventions, merges.
- `references/errors-and-retries.md` — the retry matrix and the reconciliation of an
  uncertain create.
- `references/credentials-and-safety.md` — token handling, explicit targeting, the
  production-database trap, and approval discipline.
- `references/known-unknowns.md` — what is genuinely unverified. Read this before
  claiming an upload limit, a size threshold or an option-list edge case.

## Scripts

- `scripts/check_credentials.py` — reports whether a token is available and a bounded
  target is configured, by length and effect, without ever printing the value.
- `scripts/ninox_client.py` — a small explicit-target client. Read-only by default;
  writes require both an approval flag and a non-dry-run invocation.

## Provenance

The behavioural rules in this skill are not guesses. They come from Nortex Systems'
Ninox projects: a full request-and-response trace of the classic write API, and an
end-to-end test that created, uploaded to, read back and inspected sixteen real
documents against a disposable table. Where this skill states something as verified,
that is what verified it; where something is open, `references/known-unknowns.md`
says so instead of inventing a threshold.
