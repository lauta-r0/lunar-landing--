# LunaScout — instructions for Claude Code

- Read CONTEXT.md and CONTRACT.md before doing anything. CONTRACT.md is binding; don't change it without the team's approval.
- Reply to the user in Spanish. All code, comments, docs and UI text in English.
- Every code file starts with the AI-use header from CONTRACT.md section 7.
- Never present sample or made-up data as real. Sample data must be labeled.
- Work only in your own folder and branch (see 00_PLAN.md ownership). Ask before changing files owned by another agent.
- Pull requests target develop, not main. main only receives the final reviewed version.
- Do not add AI attribution trailers or footers to commits or PRs; AI use is disclosed via the file header (CONTRACT §7) and the README.

## Ownership (from the team plan)
| Branch | Folder(s) | Agent |
|---|---|---|
| `feat/ephemeris` | `engine/ephemeris.py`, `scripts/fetch_ephemeris.py`, `data/ephemeris/` | 02 Ephemeris |
| `feat/engine` | `engine/` (except ephemeris), `scripts/prepare_dem.py`, `scripts/precompute_horizons.py`, `data/derived/` | 03 Terrain engine |
| `feat/api` | `api/`, deploy config | 04 API + deploy |
| `feat/web` | `web/` | 05 Frontend |
| — | `docs/` (validation.md, submission/) | 06 Validation, 07 Submission |

Note: `00_PLAN.md` lives in the team's `prompts/` folder outside this repo.
