# The write path

A send is three steps, in this order. The third is not optional.

1. **Create** the record.
2. **Attach** the document to the created record.
3. **Read the record back** — and the read-back is what the human is shown.

## Step 1 — create

The body nests the values under a `fields` key, and the keys of that object are the
fields' **current names**:

```json
{
  "fields": {
    "Fecha": "2026-08-08",
    "Importe": 1999,
    "Importe IVA deducible": 347,
    "Tipo": "Cargo puntual"
  }
}
```

A successful create answers **HTTP 200** with the identifier of the new record. That
identifier is what the attachment call and any deep link both need, so a create whose
response is lost to a timeout leaves the flow genuinely stuck — see
`references/errors-and-retries.md`.

**Never write a field the user has not explicitly mapped.** The consequence is not
cosmetic: because you may not assume any field exists, **no marker field may ever be
relied upon**. Duplicate prevention therefore lives read-side against your own local
history, not as a flag written into the user's table.

## Step 2 — attach

`POST .../records/{id}/files`, `multipart/form-data`, one call, expects **HTTP 200**.

- **The document attaches to the record, not to a field.** A file-type field is not
  required, no table is unsuitable, and the attachment is not a mapping target. Do not
  offer one to the user as a mapping candidate.
- Read it back with `GET .../records/{id}/files`, which returns name, size and content
  type. Verify all three against what you uploaded.
- A record created without its document is **incomplete**, never done.
- Preserve the original bytes. A document that arrived as a PDF is attached exactly as
  received; only captures assembled by the app itself are turned into a new PDF.

## Step 3 — read back, always

**Fields carrying formulas or defaults silently override the values you submitted, and
the create response does not reveal it.** So the confirmation must present the
read-back, never what was sent.

- What you show the user is what is actually stored.
- Where a default overrode a submitted value, the override is visible precisely
  because you read back.
- **Creating a record may trigger automations inside the user's database that the API
  does not expose.** The read-back is the only visibility you have into that, and
  user-facing documentation should admit it.

## Updates are merges

Fields you do not send are preserved. Therefore:

- A correction sends **only what changed**.
- A failed attachment is retried **without touching the record**.
- Send nothing, and nothing changes. A correction that leaves the rest untouched is
  the expected behaviour, not a lucky one.

## Mapping rules

A destination is the tuple of **host, team, database, table, field mapping** — plus a
per-field setting for absent values. It stores field **identifiers**; the payload is
keyed by field **names** resolved at send time from a schema cached when the app opens.
A destination that stored names would break silently the first time a column was
renamed.

### Formula and read-only fields

- They are **not mapping candidates** and must never be offered to the user.
- Writing to one returns **HTTP 500** — see `references/errors-and-retries.md`.
- Where a formula field computes a total, it is a **post-write contrast**, never a
  write target: read it back and compare it against the total you computed
  independently. Where they disagree, ask about the mapping or the formula.

### Choice fields

- Accept either the option identifier or the option **text**; reads always return the
  text.
- The mapping therefore offers the field's **existing options** and never free text,
  and the value written must be one of them.
- **Open:** behaviour when the written text matches **none** of the field's options is
  unverified. Containing the risk means offering only existing options — it does not
  eliminate it. Do not claim the case is handled.

### Absent values

A value the source does not carry is **not** automatically a zero. What to write is a
property of the user's table, not of your data, so each mapped field carries its own
setting:

- **Leave the Ninox field empty** — the default.
- **Write zero.**

Two destinations can therefore receive two different values for the same source
document, and both are correct.

## Number and date conventions

- **Dates**: a `YYYY-MM-DD` string is stored verbatim. Validate it as a real calendar
  date before sending, and decide explicitly what to do when the source has none.
- **Money**: send integers in the currency's **minor unit**, and rates as integers in
  **basis points**. Never let a float cross the boundary — an amount that round-trips
  through a binary float is an amount that can come back a cent wrong. This is a
  convention our projects adopted, not a Ninox rule; where you deviate, say so.
- **Never silently drop a value you cannot store.** If the destination table has no
  field for the gross total, record it in your own log and say so, rather than
  discarding it quietly.

## Deep link back to the record

After a successful send, offer a link to open the record in Ninox, built **entirely
from data you already hold**:

- host, team and database from the destination,
- table identifier from the destination,
- record identifier from the create response,
- and the view segment of the URL is optional, so **no additional API call** and no
  credentials are needed.

**The URL structure is verified but is not a published vendor contract.** Therefore the
action must **degrade to opening the database** if it stops resolving, rather than
showing an error.
