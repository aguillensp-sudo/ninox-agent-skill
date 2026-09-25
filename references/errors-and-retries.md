# Errors, retries and the uncertain create

Failure handling is stated as a **matrix** rather than as principles on purpose:
eleven conditions have different correct answers, the intuitive answer is wrong for
at least four of them, and nobody classifies eleven failure modes correctly at the
moment of failure.

## The matrix

| Condition | Behaviour |
| --- | --- |
| No connectivity | Queue the send, and send it automatically when connectivity returns |
| Timeout or network error on **create** | Outcome `uncertain`; reconcile read-side; **never** a blind retry |
| Timeout on attachment or on read-back | Bounded exponential backoff — neither can duplicate a record |
| `401` or `403` | An authentication problem: the human re-enters the token; no retry |
| `404` | The database or table no longer exists: send the human to the destination; no retry |
| `500` | Refresh the schema, retry **exactly once**, then report a **mapping error** rather than a server outage |
| Record created, attachment failed | Retry the attachment only |
| `4xx` other than the above | Treat as a client error and surface the response body; do not retry |

## Why a 500 is not an outage

Ninox reports a **mistyped, invalid, read-only or formula field name as HTTP 500**,
not as a `4xx` with an explanation. The consequence is that this API's `500` usually
means *your* mapping is wrong.

- A client that treats `500` as a server outage and retries indefinitely will hammer
  the API over its own mistake, drain battery and data, and tell the human the server
  is unwell. That is the failure this rule exists to prevent, and a test that
  demonstrates it is a correct test of the rule.
- The correct response: **refresh the schema**, retry **exactly once**, and on a
  second failure report a **mapping error**. Say the mapping is the suspect. Do not
  say the server is down.

## Never blind-retry a lost create

A `POST` whose response is lost to a timeout may still have created the record. The
obvious instinct — retry — is precisely what writes a duplicate into someone's
accounting. So:

- A create whose response was lost enters the **`uncertain`** state. It is **not**
  retried.
- The evidence needed to resolve it is read-side, and it exists **regardless of
  mapping**: every record carries `createdAt` and `createdBy`.
- Retries are safe for the attachment and the read-back, because neither can produce a
  second record.

## Reconciling an uncertain create

The algorithm:

1. Read the destination table's **most recently created records**, and narrow to a
   **short time window** around the attempt.
2. Compare candidates against the **mapped fields** and their submitted values.
3. Decide:
   - **Exactly one match** → adopt that record. Treat the create as having succeeded
     and continue to the attachment step as if the create had returned normally.
   - **No match** → the `POST` did not land. Create the record.
   - **Ambiguous** — more than one plausible match, or too few mapped fields to
     compare — → **ask the human**. Never guess. Surface the uncertainty and let them
     choose.
4. Whatever the outcome, **exactly one record exists** afterwards.

Two properties make this work and must be preserved:

- **It does not depend on mapping.** A destination with **no** field mapped at all
  still reconciles, because `createdAt` and `createdBy` are always available. This is
  why no marker field is required to exist — see the prohibition in
  `references/write-path.md`.
- **It stays inside what the app created.** Reconciliation is bounded to the app's
  own recently created records. Never scan or adopt records the app did not create.

## Loading the candidate records

Step 1 needs a way to fetch recent records.

- **`perPage` and `page` work:** use them to fetch a bounded page. `perPage` sets the
  page size and `page` is an offset. The default is 100 records per page.
- **Sorting is not verified:** `?order=` and `?desc=` are accepted but the actual
  ordering is not confirmed. Do not depend on server-side sort; fetch a page and sort
  locally.
- **Filter locally:** the list endpoint has no query or filter parameters that have
  been verified to work. Fetch a bounded page and filter in-memory.
- **State the bound you applied:** if a time window is used as a filter, state it
  explicitly so the next reader knows how far back the search looked.

## Errors you must not swallow

- **A failed attachment means the send is incomplete, not done.** A record that exists
  without its document must be reported as incomplete, and the retry must target the
  attachment alone.
- **Never fix data to make a check pass.** If a read-back disagrees with what was
  submitted, the disagreement *is* the data: formulas and defaults override submitted
  values legitimately. Surface it; do not rewrite the record to match your
  expectation.
- **A formula total that disagrees with your own computed total is a question about
  the mapping or the formula, not a verdict on your extraction.** Present it as such.
  And be honest about the blind spot: a total that was misread *and then used to derive
  its own components* will be reproduced by the formula, so the contrast passes. It is
  not protection against that case.
