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

## Deep links

- The URL structure **was verified but is not a published vendor contract.** It can
  change without notice. Any implementation must degrade to opening the database rather
  than failing.

## List, query and paging parameters

- The exact query, filter, sort and paging parameters of the record list endpoint are
  **vendor-documented, not verified by us**. Confirm them in the current vendor
  documentation before depending on them, and never guess a parameter name — a wrong
  parameter is one more way to earn an unexplained 500.

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
