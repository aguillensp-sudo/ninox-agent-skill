# The Ninox classic REST API

Everything under **VERIFIED** was confirmed against a live workspace while this
skill was written, or by the request-and-response trace and the sixteen-document
end-to-end test in our own projects. Everything under **DOCUMENTED** comes from the
vendor's materials. The distinction matters: do not treat a documented claim as
tested, and do not let an unverified gap be filled with a plausible guess.

## Two generations of interface

| | Classic | Newer (workspace/module) |
| --- | --- | --- |
| Organised as | teams → databases → tables | workspaces → modules |
| Credential | one personal access token | a workspace-scoped key |
| Reaches | the whole subscription the user can see | one workspace |
| Attachment upload | one `multipart/form-data` call | presigned storage URLs, three steps |
| Base URL | `https://api.ninox.com/v1` | see vendor documentation |

**DOCUMENTED:** the vendor describes the classic interface as the previous
generation. Our choice of it, and the reasoning, are recorded in ADR-003: a single
personal access token enumerates teams, then databases, then tables with their
fields — which is exactly the chain a list-driven setup needs — and upload is one
call rather than three.

**Consequence to preserve:** isolate the client behind a port. Do not let these URLs
spread through a codebase, because a second implementation has to be addable without
touching the rest of it.

## Host

**DOCUMENTED:** Ninox is offered as a private cloud on a customer-specific host,
which is common in larger German companies. The default is `api.ninox.com`; the host
is **configuration**, validated when the token is entered, and **never compiled in as
a constant**.

## Authentication

**VERIFIED:** the request carries `Authorization: Bearer <personal access token>`.

**VERIFIED by its effect:** `GET /v1/teams` answered `200` with the token resolved
from a Windows user-level environment variable. That is the honest way to check a
credential — by its effect, never by printing it.

**DOCUMENTED:** the token is a **personal** access token, so it is scoped to the
user, not to a database. It can see everything that user can see. Treat it as full
access, and never ask for, store or transmit a Ninox username or password.

## Schema endpoints

| Endpoint | Status | Verified response shape |
| --- | --- | --- |
| `GET /v1/teams` | **VERIFIED** | `200`, a list of `{id, name}` |
| `GET /v1/teams/{team}/databases` | **VERIFIED** | `200`, a list of `{id, name}` |
| `GET /v1/teams/{team}/databases/{db}` | **VERIFIED** | `200`, a `{schema, settings}` object; `schema` is identical to the dedicated schema endpoint |
| `GET /v1/teams/{team}/databases/{db}/schema` | **VERIFIED** | `200`, an object with `types[*].fields` containing all 2,143 fields; formula fields carry the key `fn` |
| `GET /v1/teams/{team}/databases/{db}/tables` | **VERIFIED** | `200`, a list of `{id, name, fields}`; **omits all 727 formula fields** — field listing returns only 1,416 of 2,143 |
| `GET /v1/teams/{team}/databases/{db}/tables/{table}` | **VERIFIED** | `200`, a `{fields, id, name}` object; same shape and field coverage as `.../tables` |
| `GET /v1/teams/{team}/databases/{db}/tables/{table}/fields` | **VERIFIED ABSENT** | `404` `End-point not found` |

Two things follow, and both cost time if you discover them the hard way:

1. **The fields come back with the tables.** The tables call already carries each
   table's `fields` array; adding `?fields=true` changed nothing. You do not need a
   second call to see the schema of a database.
2. **`.../tables/{table}/fields` does not exist.** A client written against that
   plausible-looking path gets a `404 "End-point not found"`.

### The field object

**VERIFIED** across a database — 97 tables, 2,143 fields. Two endpoints return field
objects, but they speak different languages:

#### From `.../tables` (the listing endpoint)

Each field carries:

| Key | Present on | Meaning |
| --- | --- | --- |
| `id` | every field | The **stable identifier**. Store this in configuration. |
| `name` | every field | The **current display name**. This is the payload key; it changes when a human renames the column. |
| `type` | every field | The field's kind — see the vocabulary below. |
| `choices` | `choice`, `multi` | The existing options: a list of `{id, caption, captions, order}`. |
| `referenceToTable` | `ref` | The table this field points at. |
| `reverseField` | `ref` | The `rev` field that mirrors it. |
| `referenceFromTable` | `rev` | The table the relation comes from. |
| `referenceFromField` | `rev` | The field the relation comes from. |

**Critical:** `.../tables` **omits all formula fields**. Of 2,143 fields in the
database, this endpoint returns only 1,416. The 727 formula fields are not marked —
they are absent.

#### From `.../schema` or `.../databases/{db}` (the full schema)

The same field objects carry many additional keys — vocabulary including `caption`
(display name), `base` (field kind), `values` (choices), `refTypeId`/`refFieldId`
(relations) — plus these critical ones:

| Key | Present on | Meaning |
| --- | --- | --- |
| `fn` | **formula fields only** | The formula expression (e.g. `"(D+J)"`). Its presence is the marker. A field with `fn` **cannot** be written to. |
| `base` | every field | Equivalent to `type` in `.../tables`. For formula fields, `base == "fn"`. |

> **The schema carries no read-only marker.** There is no field-level signal for
> read-only apart from the formula marker (`fn`). Expressions like `canWrite`,
> `readRoles` and `writeRoles` exist but are display rules or role grants, not
> storage properties. **The only reliable signal that a field is read-only is an
> HTTP 500 on write** — see `references/errors-and-retries.md`. The practical
> mitigation is to write only fields a human has explicitly mapped, filter out
> formula fields when building a picker (by checking `fn`), and read the error as
> a mapping error instead of as an outage.

### The `type` vocabulary

**VERIFIED** as the complete set of values present across a whole subscription:

`number` · `string` · `date` · `boolean` · `choice` · `multi` · `ref` · `rev` ·
`phone` · `email` · `html` · `link` · `location` · `timeinterval` · `icon`

Read this list as observed in one workspace, not as an exhaustive vendor enumeration:
a type that a different workspace uses may not appear here. Where you meet an unknown
type, treat the field as **not** safely writable until you have established what it
accepts.

Notes on the entries that surprise people:

- `ref` and `rev` are two halves of one relation. In the subscription measured they
  appear in equal numbers (1,401 each), which is what a paired relation looks like.
  **Inference, not verified:** a `rev` field reads as the reverse view of a relation
  and is probably not a value you write. Confirm before relying on it.
- `multi` carries `choices` like `choice` does, and is the multi-select counterpart.
- There is **no** `formula`, no `readonly` and no `file`/`attachment` entry. Files are
  not fields at all — see the files endpoint below.

## Record endpoints

| Endpoint | Status | Verified behaviour |
| --- | --- | --- |
| `GET .../tables/{table}/records` | **VERIFIED** | `200`, a **list** of `{id, fields, createdAt, createdBy, modifiedAt, modifiedBy, sequence}` |
| `GET .../records/{id}` | **VERIFIED** | `200`, an object with `id` and `fields` |
| `POST .../records` | **VERIFIED** | `200` with the identifier of the new record |
| `POST .../records/{id}/files` | **VERIFIED** | `200`, `multipart/form-data` |
| `GET .../records/{id}/files` | **VERIFIED** | `200`, with name, size and content type |
| `DELETE .../records/{id}` | **DOCUMENTED, not verified by us** | A delete is a **write**: ask the human first |

The path prefix is `/v1/teams/{team}/databases/{db}/tables/{table}` throughout.

### What a record looks like

```json
{
  "id": "...",
  "fields": { "<field name>": "<value>" },
  "createdAt": "...",
  "createdBy": "...",
  "modifiedAt": "...",
  "modifiedBy": "...",
  "sequence": 0
}
```

**`createdAt` and `createdBy` are present on every record regardless of mapping.**
That is not trivia — it is the evidence that makes read-side reconciliation of an
uncertain create possible, and it is why no marker field has to exist in the user's
table. See `references/errors-and-retries.md`.

Note also that this is a **flat `fields` object**, not an array of typed values. The
keys are field names.

### Writing

The body nests values under a `fields` key, keyed by current field **name**:

```json
{ "fields": { "Fecha": "2026-08-08", "Importe": 1999 } }
```

A successful create answers **`200`** — not `201` — with the new record's identifier.
That identifier is what the attachment call and any deep link need, which is exactly
why a create whose response is lost leaves the flow stuck rather than merely slow.

### Attachments

- `POST .../records/{id}/files`, `multipart/form-data`, one call, `200`.
- The file attaches to the **record**, not to a field. No file-type field is required
  and no table is unsuitable.
- `GET .../records/{id}/files` returns name, size and content type — read it back and
  compare all three against what you uploaded.
- **VERIFIED LIMITS:** the maximum file size, the behaviour of a multi-page PDF near
  it, and real upload timings are **not established**. Do not state a threshold.

## Status codes and error bodies

| Code | Meaning in this API | What to do |
| --- | --- | --- |
| `200` | Success — including create and upload | Continue |
| `401` / `403` | The token is absent, expired, revoked or lacks access | Ask the human for a token; no retry |
| `404` | The team, database, table or endpoint does not exist | Check the target. For an endpoint, check the path — see the absent fields endpoint above |
| **`500`** | **Usually a bad, formula or read-only field name** | Refresh the schema, retry **once**, then report a **mapping error** |

**VERIFIED error body shape:** at least some errors are a small JSON object with a
`message`, for example `{"message":"Team Not Found"}` returned with a `404`. Report the
body; it is more useful than the status alone.

**The `500` row is the one that matters.** It is the single most counter-intuitive
behaviour of this API: the status that universally means "the server is unwell" here
usually means "you named a field wrong". A client that retries it forever hammers the
API over its own mapping mistake.

## Query parameters

**Paging parameters (records endpoint):**

| Parameter | Verified |
| --- | --- |
| `?perPage=N` | **Works.** Honoured above the default. Tested with 2, 200, 1000; `perPage=1000` returned all 1,000 records. |
| `?page=N` | **Works.** An offset: `page=50&perPage=2` returned a different pair than `page=0`, so it is not a no-op. |
| Default (no parameters) | **Paged to 100.** An unparameterised call returns 100 records, not the whole table. Any code treating it as "the whole table" is wrong on tables with 100+ rows. |
| `?limit=N` and `?pageSize=N` | **Both ignored.** `?limit=2` and `?pageSize=2` returned `200` and the whole table; neither bounded the result set. Do not use these names. |
| `?sinceSq=N` | **Unverified.** Tested once, returned the full default page; whether it filters, orders or expects a different coordinate is unknown. |
| `?order=` and `?desc=` | **Accepted, order not verified.** `?order=_id&desc=true&perPage=2` returned `200` with 2 records, but whether it actually ordered by `_id` was not confirmed — only that it returned the right count. |

**Consequence:** **always supply `perPage` and `page`** when you need to bound a result
set. Fetch and bound **locally** if the server-side order is uncertain. Do not assume
server-side filtering or sorting exist; where required, fetch the records and filter
in-memory. The `sequence` field is present but not guaranteed to order the default
response (tested baseline showed it out of order), and `sinceSq` remains open.

See `references/known-unknowns.md` for what genuinely remains unverified.

## Deep links

A record can be opened in Ninox from a URL built entirely from data you already hold:
the host, team and database from the destination, the table identifier from the
destination, and the record identifier from the create response. The view segment of
the URL was found to be optional, so **no extra API call and no credentials** are
needed.

**This structure was verified but is not a published vendor contract.** It can change
without notice, so the action must degrade to opening the database rather than showing
an error.

## What this file deliberately does not claim

- A maximum upload size, or any timing figure.
- An exhaustive list of field `type` values.
- The existence of any query, filter, sort or paging parameter.
- That the classic interface will keep working indefinitely — only that no deprecation
  date has been confirmed to us.
