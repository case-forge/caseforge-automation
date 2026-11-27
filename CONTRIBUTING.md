# Contributing

Thank you for your interest. Please read this before you open an issue or a pull request.

## Licence first

The project is licensed under FSL-1.1-MIT (see `LICENSE`). By sending a pull request you agree that your contribution is licensed under the same terms, and that CaseForge may also distribute it under other licence terms. Pull requests need that agreement confirmed before they are merged.

## Issues

- Bugs: say what you ran, what you expected and what happened. Include the command and the error, not a screenshot of it.
- Never include client data, real names, addresses, case numbers, email content or secrets in an issue, a pull request, a test or a log, even redacted by hand. Use the synthetic firm in `profile/firm.example.yaml` and made-up people.
- Security problems go by email, not as issues. See [SECURITY.md](SECURITY.md).

## Pull requests

- Keep each one to a single change, with a commit message that says what changed and why.
- Run the tests before you push: `python3 -m pytest -q -n auto`, and for the CRM, `npm test` in its folder.
- Add or update a test for any change in behaviour. A safety rule needs a test that fails when the rule is broken.
- Describe a new tool, or a change to one, in the tool's own module docstring (what it is and how to run it) and put the history in the commit message.
- Put firm-specific values in the firm profile, not in code. In the CRM, a test fails on a firm value anywhere outside `lib/firm.ts`.
- Do not add a dependency under the GPL or AGPL to the Python process or the CRM bundle. Record the licence of any new dependency in `NOTICE`.

## Design rules a change must keep

- Nothing is sent automatically. Code makes drafts and a person sends them.
- Code decides and models assist. A model's output is checked in code before it is used, and a model never writes to the database directly.
- Unknown facts stay `TBC` and are shown to a person, never guessed.
- C8-protected contact details never reach a respondent-facing document.
- Client data is reached through the hub API, so the exposure audit and the change log see it.

## Style

British English, plain words, short sentences. Python follows the existing modules: standard library first, type hints, no network calls in unit tests.
