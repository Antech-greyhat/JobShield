# JobShield

JobShield helps job seekers check recruitment listings for scam indicators. Its
Python backend provides offline analysis, local scan history, batch imports,
company-directory checks, and report review. The repository also contains a
Chrome extension.

## Run the Python tools

Use Python 3.10 or later from this checkout. All Python functionality uses the
standard library; no pip installation or external service is needed.

```sh
python -m jobshield scan --text "Hiring now. Salary available. Pay for training via mpesa." --json
python -m jobshield assess --file examples/posting.json --json
python -m jobshield batch --file examples/jobs.csv --output results.json
python -m jobshield --help
```

`python jobshield.py --text ...`, `--file ...`, and `--stdin` remain supported.
The text scanner can also be imported directly:

```python
from jobshield import analyze_job_text

result = analyze_job_text("Job description: Developer. Responsibilities: Build tools. Salary: KES 100,000.")
print(result["score"], result["status"])
```

Keep the `jobshield` package and `data` directory together. The scanner loads
the extension's `data/scamkeywords.json`; company checks load
`data/verifiedcompanies.json`. `--rules path/to/rules.json` selects custom rules
for `scan`, `assess`, `batch`, or `serve`. Rules need a unique, non-empty `term`,
an integer `weight` from 1 to 100, and a non-empty `description`.

## Analysis modes

`scan` matches the browser's `scripts/scanner.js` text-scoring behavior. It
requires at least two distinct job indicator phrases, starts at 100, subtracts
each matched scam phrase's weight once, and subtracts 10 if neither `salary` nor
`pay` appears. Scores below 40 are `danger`, 40-69 are `warning`, and 70-100 are
`safe`. Text without enough job indicators is `unknown`.

`assess` adds checks for upfront fees, urgency, personal recruiter email,
company-domain mismatches, missing company websites, and messaging-app interviews.
Company-directory matches provide evidence without increasing the score or
certifying a recruiter. A fee already scored by the text scanner is not charged
again for the structured application-fee field. Non-job text stays `unknown`.
These scores describe heuristics; employers still need independent verification.

A structured posting uses these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `text` | string, required | Posting text, up to 200,000 characters |
| `title` | string | Job title |
| `company_name` | string | Claimed employer |
| `company_website` | HTTP(S) URL | Company website for domain comparison |
| `recruiter_email` | email | Recruiter address |
| `application_fee` | boolean | Whether payment is requested |
| `interview_method` | string | `phone`, `video`, `in_person`, `telegram`, or `whatsapp` |
| `url` | HTTP(S) URL | Original posting link |

Optional strings default to empty; `application_fee` defaults to false. Unknown
fields and invalid types are rejected. A missing website adds a penalty only
when company, recruiter, fee, or interview details have been supplied.

Saved HTML is supported with `assess --file posting.html`. The reader removes
scripts, styles, and explicitly hidden content and recognizes a single
Schema.org `JobPosting` JSON-LD record. It does not download pages, run JavaScript,
or render CSS. JSON-LD descriptions and company details are used when available;
otherwise visible markup text is used. Multiple job records require separate files.

## Local history and reports

Scans are not persisted unless `--save` is supplied. Saved postings, results,
reports, and review events live in `.jobshield/jobshield.sqlite3`, which is ignored
by Git. Set a different database with `--db PATH` before the subcommand.

```sh
python -m jobshield assess --file examples/posting.json --save --json
python -m jobshield history --limit 20
python -m jobshield history --status danger
python -m jobshield stats
python -m jobshield companies --query safaricom
python -m jobshield report --company "Example" --url "https://example.com/jobs/1" --reason "Requests an application fee."
python -m jobshield reports --status pending
```

Read a complete saved scan with `history --id ID`, and remove only that scan with
`delete-scan ID`. Review a report using the `id` and current `version` returned by
`reports --id ID`:

```sh
python -m jobshield review REPORT_ID --status approved --note "Checked the fee request." --version 1
```

Reports start as `pending` and can be `approved` or `dismissed`. A reviewed report
must first be reopened as `pending` before another decision. Every transition
records a note, timestamp, and version. Stale reviews return a conflict instead
of overwriting a newer review. These reports stay in the local database; they
are not submitted to any company or external service.

## Batch imports and exports

`batch` accepts a JSON array, JSONL records, or CSV with a `text` header and any
other posting fields. CSV booleans accept true/false, yes/no, or 1/0. Files must
use UTF-8. Batches contain at most 500 postings and 10 MB of source data.

```sh
python -m jobshield batch --file examples/jobs.csv --output results.csv --output-format csv
```

Structural file errors stop the import. Invalid individual postings are returned
in an `errors` array while valid postings are analyzed. With `--save`, successful
rows are saved individually; a batch is not an all-or-nothing transaction. Results
retain source record order, scores, flags, and validation errors. Spreadsheet
formula cells are escaped in CSV exports. File output is replaced atomically and
cannot overwrite the input file.

Exit code 0 means successful execution, including danger or unknown results.
Code 1 means a batch completed with invalid rows. Code 2 means an invalid command,
file, rule set, or database operation. The CLI rejects empty text; the imported
`analyze_job_text("")` function returns `unknown` to match the browser scanner.

## Local HTTP API

```sh
python -m jobshield serve --port 8765
```

The API binds to `127.0.0.1` and prints a session bearer token. Set
`JOBSHIELD_API_TOKEN` to a token of at least 32 ASCII characters to reuse a token
between runs. Only `/health` is public. Browser callers also need an explicit
`--allow-origin http://localhost:5173` or `--allow-origin chrome-extension://EXTENSION_ID`.
See [the API reference](docs/api.md) for requests, responses, and error handling.

## Browser extension

Open `chrome://extensions`, enable Developer mode, choose **Load unpacked**, and
select this repository. The existing extension runs independently; it does not
automatically connect to the Python API or share its local database. To rebuild
Tailwind CSS, run `npm ci` and `npm run build`.

## Development

```sh
python -m unittest discover -s tests -v
```

Tests cover scoring, company-domain spoofing, imports, persistence, concurrent
review conflicts, CLI workflows, and the actual local HTTP server. Node.js enables
a parity test against the browser scanner for all shared scam-rule combinations;
that test is skipped if Node.js is absent. CI runs Python 3.10 and 3.14 with Node 24.

Python is implemented as application source in `jobshield/`. There are no GitHub
language-statistics overrides. GitHub measures source by bytes and normally
excludes third-party dependencies such as `node_modules`. Its repository language
bar reflects the default branch, so it updates after changes reach `master` and
GitHub recalculates the breakdown.
