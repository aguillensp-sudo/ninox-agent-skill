# Schema and fields

## The model

```
team
└── database
    └── table
        └── field
            └── record   ← values live here
```

- A **team** is the top-level unit.
- A **database** belongs to a team.
- A **table** belongs to a database and is addressed by a **short identifier**
  (for example `YB`), not by its display name. Display names are for humans and are
  not stable addresses.
- A **field** belongs to a table and carries both a **stable identifier** and a
  **current name**.
- A **record** is a row. Its values are keyed by field **name**.

One personal access token enumerates this chain: teams, then their databases, then the
tables of a database together with their fields. That is what makes a list-driven setup
possible — the user **chooses** rather than types, which is why identifiers are never
hand-entered.

## Identifiers versus names — the single most important distinction

| | Identifier | Name |
| --- | --- | --- |
| Stability | Stable; it survives a rename | Changes whenever a human renames the column |
| Used in | Your **configuration** — the stored destination | The **payload** — the `fields` object's keys |
| Resolved | — | At **send time**, from a schema cached when the app opens |

Rules:

- **Store identifiers. Send names.** A destination that stored field names would break
  silently the first time somebody renamed a column: you would write to a field that no
  longer exists, and the API's answer to that is an HTTP 500 that reads like an outage.
- **Resolve the current name at send time** from a schema you cached when you started.
  Do not cache names for longer than that.
- **Refresh the schema on a 500** before the single retry. A rename is one of the
  things a 500 is telling you.
- **Never hand an identifier to the payload** and never hand a name to the stored
  configuration.

The exact key names used for these two values in the schema response are
vendor-documented rather than project-verified — confirm them against
`references/rest-api.md` before parsing.

## Field kinds, and what each means for you

You must read a field's kind **from the schema**. Do not infer it from the field's
name, from the display name, or from what previous records happened to contain.

The `type` values observed across a whole subscription are:

`number` · `string` · `date` · `boolean` · `choice` · `multi` · `ref` · `rev` ·
`phone` · `email` · `html` · `link` · `location` · `timeinterval` · `icon`

| Kind | Writable? | Notes |
| --- | --- | --- |
| `string` | Yes | Send a string. |
| `number` | Yes | See the money convention in `references/write-path.md`; never send a float across the boundary. |
| `date` | Yes | A `YYYY-MM-DD` string is stored **verbatim**. |
| `choice` / `multi` | Yes | Accepts the option identifier **or** the option text; reads return the text. Offer only the field's existing options, which the schema supplies as `choices`. |
| `boolean` | Yes | Send a real boolean, not `"true"`. |
| `ref` | Yes, with care | Points at another table (`referenceToTable`). The target record must exist. Never create or alter the referenced record to make a write succeed. |
| `rev` | Probably not | The reverse half of a relation (`referenceFromTable`/`referenceFromField`). Inference, not verified — confirm before writing. |
| `phone`, `email`, `html`, `link`, `location`, `timeinterval`, `icon` | Treat as unverified | Documented by their names, not established by us. Establish the accepted representation before writing, or ask the human. |
| **Attachments** | **Not a field target** | Files are not fields at all in the schema. They attach to the *record* via the files endpoint. |

### The formula trap: the schema does not mark them

The natural design — "offer as mapping candidates every field the schema marks as
writable, and exclude the ones it marks as formula or read-only" — **cannot be built
on this API.** A sweep of 8,048 fields across 566 tables found no `formula`,
`readonly`, `read-only` or `computed` marker anywhere. A field object carries only
`id`, `name`, `type`, plus `choices` for choice fields and the reference keys for
relations.

So you cannot tell a formula field from a writable one by reading the schema. What
follows:

- **Write only fields a human has explicitly mapped.** That is the only reliable
  filter, because it is a human decision rather than an inferred one.
- **Read `HTTP 500` as a mapping error**, refresh the schema, retry once, then report
  a mapping error. Do not report an outage.
- Where a formula field computes a total, use it as a **post-write contrast** — read
  it back and compare — and never as a write target.
- If a design document claims the schema marks formula fields, that claim is wrong and
  the design is built on a marker that does not exist. Say so rather than implementing
  around it.

**Never create, alter or delete schema.** You may not add a field, rename a column, or
change a table's shape to make your write fit. The user's database is theirs; if a
value has nowhere to go, that is a question for the human, not a migration you perform.

## Choice fields in detail

**VERIFIED:** a choice field carries its options in the schema, as `choices` — a list
of `{id, caption, captions, order}`. The `caption` is the option text and the `id` is
the option identifier; `captions` is an object used for per-language captions and is
empty in the workspaces we measured. A `multi` field carries `choices` in the same
shape.

- The mapping picker shows the field's **own** options — read them from `choices` —
  and free text is not accepted as a configuration, because a text matching no option
  has unverified behaviour.
- Write either the option **identifier** or the option **text**; reads always return
  the **text**, so compare on text.
- Present the options in their `order`, which is the order the user chose in Ninox.
- **Unverified:** what happens when a value is written that matches none of the
  options. Keep this out of scope by construction, and do not describe the case as
  handled.

## Reading a schema safely

- Reading the schema is a **read**. It is safe, expected and does not require the
  human's approval.
- Reading the schema of a client's production database is still a read of their
  business structure. Report field **names and kinds**, not record contents, and do not
  paste a whole schema into a transcript when a summary answers the question.
- Cache the schema for the duration of one operation, and refresh it deliberately
  rather than on every call — but never let a stale cache survive a 500.

## A worked example of the whole chain

The end-to-end verification in our projects created records in a disposable table
addressed as `YB` ("Tarjetas Banco"): it wrote four mapped fields plus an attachment,
read each record back, confirmed a formula-computed total as a contrast, and verified
the attached file's name, size and content type from the files endpoint. Sixteen real
documents went through that path, all uploads answering HTTP 200.

That is the shape to copy: a disposable or test table, a bounded set of mapped fields,
a real read-back, and a delete you asked permission for.
