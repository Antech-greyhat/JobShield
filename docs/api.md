# Local JobShield API

Run `python -m jobshield serve`. The default address is
`http://127.0.0.1:8765`. A different port can be supplied with `--port`; a different
database uses the global `--db PATH` option before `serve`.

All data endpoints require `Authorization: Bearer TOKEN`. The token is read from
`JOBSHIELD_API_TOKEN`, or generated and displayed once at startup. Tokens need at
least 32 ASCII characters without whitespace. HTTP bodies use UTF-8 JSON with
`Content-Type: application/json` and `Content-Length`. Request bodies are limited
to 1 MB. Duplicate JSON keys and non-finite numeric values are rejected.

For browser clients, add each exact localhost or Chrome extension origin with
`--allow-origin`. CORS preflight requests do not need a token; the actual request
does. There are no wildcard origins, automatic outbound network calls, or remote
bindings. This standard-library server is intended for local development and
desktop clients.

## Endpoints

| Method | Path | Operation |
| --- | --- | --- |
| GET | `/health` | Public version and availability check |
| POST | `/v1/scans` | Analyze a structured posting; optionally save it |
| GET | `/v1/scans` | List saved scan summaries |
| GET | `/v1/scans/{id}` | Read a saved posting and its full analysis |
| DELETE | `/v1/scans/{id}` | Delete one saved scan |
| POST | `/v1/batch` | Analyze up to 500 posting objects |
| GET | `/v1/companies?q=term` | Search the bundled company directory |
| GET | `/v1/rules` | Read the active text-scanning rules |
| POST | `/v1/reports` | Submit a report to the local review queue |
| GET | `/v1/reports` | List reports |
| GET | `/v1/reports/{id}` | Read a report and its audit events |
| PATCH | `/v1/reports/{id}` | Review or reopen a report |
| GET | `/v1/stats?days=30` | Summarize stored scans and reports |

Scan/report list queries accept `limit` (1-200, default 50), `offset` (default 0),
`status`, and `q` (literal company-name search). Duplicate and unsupported query
parameters are rejected. List responses use `items`, `total`, `limit`, and
`offset`. Scan summaries omit posting text; retrieve an individual scan for it.

## Scan a posting

`POST /v1/scans`:

```json
{
  "posting": {
    "text": "Job description: Engineer. Responsibilities: Build tools. Salary available.",
    "company_name": "Safaricom",
    "company_website": "https://safaricom.co.ke",
    "recruiter_email": "hiring@safaricom.co.ke"
  },
  "save": false
}
```

The `posting` schema is documented in the project README. The response has a
normalized `posting` and an `analysis` with:

- `score`, `status`, and `flags` for the combined result;
- `text_analysis` for the original browser-compatible score;
- `additional_risks` with codes, messages, weights, and levels;
- `positive_signals` and `company_identity` evidence;
- a notice explaining the heuristic nature of the assessment.

The default unsaved request returns 200 and does not create a database. With
`save: true`, it returns 201 and also includes `id`, UTC `created_at`, `title`,
`company_name`, `source`, `score`, and `status` for the saved record. A scan
classified as danger is still a successful HTTP request. Deleting a saved scan
returns 204 with no body; an unknown ID returns 404.

## Batch analysis

`POST /v1/batch` accepts `{"postings": [{"text": "..."}], "save": false}`.
Its response contains `items`, `errors`, and `summary`. Each item/error includes
a one-based `row` index; summaries contain total, successful, failed, and
per-status counts. Input validation failures on individual postings do not
discard successful rows. With `save: true`, successful rows persist individually.
An HTTP 200 batch response can contain row errors, so inspect `summary.failed`.
The 1 MB HTTP body limit still applies to batches; the CLI supports larger files.

## Report lifecycle

Create a report with `POST /v1/reports`:

```json
{
  "company_name": "Example",
  "job_url": "https://example.com/jobs/1",
  "reason": "An application fee was requested."
}
```

The 201 response includes a generated `id`, `status: "pending"`, `version: 1`,
and the first audit event. Approve it with `PATCH /v1/reports/{id}`:

```json
{
  "status": "approved",
  "note": "Checked the supplied evidence.",
  "version": 1
}
```

Use the current version from the report. A successful review increments it and
adds an event. `pending` reports can become `approved` or `dismissed`. Reviewed
reports can become `pending` again; reopen before changing the decision. Notes
are mandatory. A stale version, unchanged status, or invalid transition returns
409 without modifying the report or adding an event. Approval records a local
review decision; it does not add a company to the verified-company directory.

## Statistics

`GET /v1/stats` returns all-time scan/report counts by status and an average scan
score excluding `unknown` results. `daily_scans` contains UTC daily scan and danger
counts during the last `days` days (1-365). Days without scans are omitted. The
`days` filter affects only the daily series, not the all-time totals.

## Errors

Errors are JSON objects such as:

```json
{"error": {"code": "invalid_input", "message": "text is required."}}
```

| Status | Meaning |
| --- | --- |
| 400 | Invalid JSON, posting fields, or query parameters |
| 401 | Missing or incorrect bearer token |
| 403 | Host or browser origin denied |
| 404 | Unknown endpoint, scan, or report |
| 405 | Unsupported operation on an endpoint |
| 408 | Timed out while reading a request |
| 409 | Report review conflict |
| 411 | Missing or duplicate Content-Length |
| 413 | Request body outside the allowed size |
| 415 | Body is not application/json |
| 503 | Local database unavailable |

Responses disable caching. Database details are logged locally and not included
in API errors. Tokens and request bodies are not written to request logs.
