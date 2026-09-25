# Known unknowns

A skill that hides its gaps is worse than one that lists them, because a plausible
invented threshold gets treated as a specification. Everything below is **open**. Do
not state any of it as fact, do not invent a number to fill a gap, and do not let a
requirement depend on it.

## Attachment upload limits

- **The maximum file size is not established.** Do not state a limit, and do not build
  a check against one. The basic contract *is* verified: one `multipart/form-data` call
  to the record's files endpoint, HTTP 200, verified with a disposable record and then
  with sixteen real uploads.
- **A multi-page PDF near that limit is untested.**
- **Upload timings from a real user's network are unmeasured.** Measurements taken from
  a cloud container are not a substitute, and should not be presented as one.

If a requirement needs a threshold, the honest options are: test it and record the
result, or state that no threshold is claimed. Inventing one asserts something untested.

## Choice fields

- **Writing text that matches none of a field's options is unverified in every test so
  far.** Offering only existing options contains the risk; it does not close it.

## Private cloud

- **A customer-specific host is specified but has not been re-verified against a real
  private instance.** The behaviour is testable and the configuration is mandatory, but
  that particular verification has not been done.

## Formula-contrast blind spot

- Reading a formula total back and comparing it against your own total **does not catch
  a total that was misread and then used to derive its own components**: the formula
  reproduces the error and the contrast passes. Do not present the contrast as
  protection against that case. The real protection is a read-before-derive rule in
  whatever produces the values.

## Schema endpoints and `fn`

- **`GET .../schema` and `GET .../databases/{db}` return a large, internal-looking
  payload.** The schema is ~1.5 MB in the test database and carries editor state
  (`viewConfig`, `tooltips`, `uuid`, `seq`) that reads as workspace serialisation
  rather than a published contract. The vendor may change this shape without notice.
  A client must **isolate** the schema behind an adapter and **degrade** if `fn`
  disappears.
- **Password-encrypted schemas are untested.** If a database carries a password,
  the vendor documentation states the schema may be encrypted. This was not observed
  in the test database (`settings.lock` was `false`), and whether an encrypted payload
  is undecryptable or merely opaque to a client remains unknown.
- **One formula field carried `fn` as an empty string.** Its meaning is unknown: an
  emptied formula, or a formula field whose expression was cleared but whose kind was
  not converted. A client filtering on the presence of `fn` will treat it as a formula;
  that may or may not be right.

## Deep links

- The URL structure **was verified but is not a published vendor contract.** It can
  change without notice. Any implementation must degrade to opening the database rather
  than failing.

## List, query and paging parameters

- **`perPage` and `page` work.** They were re-verified on 2026-09-25.
- **`?order=` and `?desc=` are accepted but their actual ordering is unverified.** A
  query with those parameters answered `200` with the correct record count, but the
  sort order was not confirmed — it may or may not actually sort. Before depending on
  server-side ordering, fetch and sort locally.
- **`?sinceSq=N` is unverified.** It was tested once, returned the default page, and
  whether it filters, orders, or expects a different value is unknown.
- **Never invent a parameter name.** A wrong parameter is one more way to earn an
  unexplained 500.

## Interface deprecation

- The classic interface this skill documents is described by the vendor as the
  **previous generation**. There is no announced deprecation date that we have
  confirmed. Isolate the client behind a port so a second implementation can replace it
  without touching the rest of the system, and re-check the vendor's position before
  starting anything long-lived.

## Naming and trademark

- A product name built on this platform has not necessarily been checked in the app
  stores or at the EUIPO. That is a business check, not a technical one, and it is not
  done.

## How to close one of these

Test it against a **disposable table**, with a bounded number of mapped fields, a real
read-back, and a delete you have asked permission for. Record the exact request, the
exact response and the date. Then update this file — a gap closed in a test and left
open here will be re-discovered by error.
