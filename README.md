# job-agent

A job-application helper for Claude Code. A small Python tool reads the job boards of companies
you pick, filters the roles by your rules and plans an answer for every application question
from your profile. A Claude Code agent then fills each application in your own Chrome and stops
at the Submit button. You review the form and click Submit yourself.

The tool spends no model tokens. The agent runs on your Claude plan.

## What you need

- Python 3.12 or newer and [uv](https://docs.astral.sh/uv/)
- [Claude Code](https://docs.claude.com/en/docs/claude-code/overview)
- Google Chrome with the Claude in Chrome extension, signed in to your Claude account

## Set up

    git clone https://github.com/JayeshSuryavanshi/job-agent.git
    cd job-agent
    uv sync
    claude --agent job-hunter --chrome

The agent lives in `.claude/agents/job-hunter.md`, so Claude Code finds it when you start it in
this folder. On the first run it copies `config.example/` to `data/` and fills in your profile
with you, one question at a time. To do that part by hand instead, run
`cp -R config.example data`, edit the files in `data/`, then `uv run job-agent check`.

`data/` is git-ignored. It holds your personal details, answers, resumes and history, so never
commit it.

## Use it

Start a session from the repo folder:

    claude --agent job-hunter --chrome

1. The agent searches for new roles (a couple of minutes) and lists the ones ready to apply.
2. Tell it which ones to do.
3. It opens each form in a new Chrome tab, fills every field and stops at Submit.
4. Look the form over and click Submit. If the site asks for an emailed code or a CAPTCHA,
   that part is yours.
5. Type "sent". It logs the role so it is never offered again.

If it asks something it doesn't know, answer it; it saves the answer for next time. If Claude
Code's auto mode blocks it from typing into forms, start it with `--permission-mode manual` and
approve its steps yourself. Chrome form filling is slow and uses your plan, so do a few roles per
sitting.

## The tool on its own

    uv run job-agent run            # find, filter and plan; writes data/runs/<time>.md and data/questions.md
    uv run job-agent questions      # questions waiting for your answer
    uv run job-agent show <link>    # may this role be sent, plus every planned answer
    uv run job-agent record <link> --resume <variant>   # log an application you sent
    uv run job-agent check          # validate the config files and resume copies
    uv run job-agent sync-resumes   # copy your current resume PDFs into data/resumes

## Your files

- `persona.yaml`: name, contact, location, links, work authorization, current job, EEO choices,
  office days you accept, and what the tool may agree to for you.
- `answers.yaml`: saved answers to form questions, matched by phrase.
- `search.yaml`: title patterns, the places you can commute to, your pay floor and the caps.
- `watchlist.yaml`: companies whose job boards are read (Greenhouse, Ashby or Lever, with the
  board slug from the company's careers URL).
- `history.yaml`: companies to skip (your current employer, say) and applications you sent before.
- `resumes.yaml`: your resume files and the keywords that pick one for each role.

## How it works

1. Find: reads the public job feeds of the companies in your watchlist.
2. Filter: title, location (your commute area or US remote), blocked companies, past
   applications, a per-company cap, posting age, posted base pay above your floor, and, if you
   need visa sponsorship, no "we don't sponsor" language.
3. Plan: picks a resume by keywords, then answers each form field from `persona.yaml`,
   `answers.yaml` or a computed value (start date, how you heard about the role). Anything it
   can't answer goes to `data/questions.md` and holds that application.
4. Apply: the agent fills the form in your Chrome. You submit.

## Rules

- It never guesses. A required question with no saved answer holds the application.
- Attestations (AI-use policies, "I personally completed this", arbitration) and postings that
  restrict AI use wait for your decision. Only an answer you save for that company covers them.
  `consents` in `persona.yaml` can pre-approve arbitration agreements, interview recording and
  confidentiality notices.
- Caps: 2 applications per company in 90 days and 10 a day by default (`search.yaml` `limits`).
- The agent never clicks Submit, signs in, creates accounts, types passwords, solves CAPTCHAs or
  works around bot checks.

## Use it responsibly

You are responsible for every application you send, so keep your answers true. Respect each
site's terms; the tool only reads public job feeds and logs in nowhere. Don't use it to
mass-apply: the caps are there so recruiters get applications you would stand behind.

## License

MIT. See `LICENSE` and `THIRD_PARTY_NOTICES.md`.
