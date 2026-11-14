# SaaS Support Case Workbench

A small, offline Python command-line project for practicing structured support
investigations. Choose a synthetic SaaS support case and get a troubleshooting
checklist plus a draft handoff for an engineering team.

This is a learning demo, not an official product integration, a production
diagnostic tool, or a substitute for checking authorized logs and dashboards.
All example cases are fictional. The program makes no network requests and
does not use AI to guess a root cause.

## What it does

- Lists fictional customer-support cases.
- Groups the symptoms into a starting investigation area (authentication,
  request/input, server/dependency, or general behavior).
- Suggests practical checks without declaring an unverified root cause.
- Creates a short handoff with the request ID, impact, observed status, and
  investigation questions.
- Can print JSON for reuse in a test or another local tool.

## Run it on Windows

You need Python 3.10 or newer. The project uses only Python's standard
library; no `pip install` step is required.

Open PowerShell in this project folder and run:

```powershell
python app.py --list-cases
python app.py --case-id CASE-1001
```

Print a machine-readable report:

```powershell
python app.py --case-id CASE-1002 --json
```

Run the automated tests:

```powershell
python -m unittest discover -s tests -v
```

If Windows does not recognize `python`, install Python and enable the
**Add Python to PATH** option, or try the `py` launcher instead:

```powershell
py app.py --list-cases
py -m unittest discover -s tests -v
```

## Example workflow

1. List the available fictional cases.
2. Select a case ID and read the observed facts.
3. Use the checklist as a starting point, not proof of a cause.
4. Verify each relevant item using approved company tools and sanitized data.
5. Edit the handoff with verified evidence before escalating it.

## Project files

| File | Purpose |
| --- | --- |
| `app.py` | Loads and validates cases, analyzes symptoms, and runs the CLI. |
| `data/cases.json` | Fictional case records used by the demo. |
| `tests/test_app.py` | Tests case validation, analysis, and command output. |

## Skills demonstrated

- Python functions, JSON input, validation, and error handling.
- HTTP status-code concepts and basic API troubleshooting.
- Structured problem solving and careful escalation notes.
- Automated tests with Python's built-in `unittest`.
- Clear distinction between observed facts and hypotheses.

## Limitations and future improvements

This demo does not connect to a real ticketing system, cloud service, customer
account, API, or log platform. Its sample facts are provided in advance; it
does not confirm whether a real incident is occurring or measure an SLA.
Recommendations are simple rules, not a diagnosis.

Possible next steps include adding a locally hosted web interface, importing
an approved case export with stricter privacy controls, and saving reviewed
handoffs. Any production use would require security, privacy, access-control,
and operational review.
