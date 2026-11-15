<!-- Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team. -->
# LunaScout — final pre-submission checklist

Deadline: **Sunday 15 Nov 2026, 23:59 local time (Uruguay, UTC−3)**. Plan: first "Submit for Judging" around **19:00**, final one before **23:00**. Resubmitting is allowed; **only the last saved submission counts.**

> **Source note.** This list is built from the brief the team gave us and from `CONTEXT.md` §8 / `00_PLAN.md`. The official Space Apps *Project Submission Guide* PDF was **not available** when this was written. `[TO VERIFY]` each item that says so against the guide before the final submit.

Tick each box only after you have checked it yourself.

## A. Team and form

- [ ] All 4 members are **confirmed on the team at the same Local Event** (Space Apps profile → team page). `[TO VERIFY]` in the guide whether every member must confirm.
- [ ] All required form fields are filled (project name, summary, demo link, final-project link, detailed description, SI use, NASA data, partner data/references). Text comes from `project_page.md`.
- [ ] Every placeholder is replaced: `[TEAM NAME]`, `[NAME 1]`–`[NAME 4]`, `[DEMO LINK]`, and no `[TO VERIFY]` is left in anything submitted.
- [ ] The summary is about 150–200 words and the detailed description is 600–900 words (`project_page.md` has 199 and 892).
- [ ] **Everything is in English** (form, README, slides, subtitles, UI). Only the video voice-over may be in Spanish.

## B. Demo (choose one; the other is not submitted)

**Video**
- [ ] Length **≤ 30.0 s** measured on the exported file (not the editor timeline).
- [ ] English subtitles visible (burned in or a caption track).
- [ ] Voice-over matches the numbers on screen; numbers match the live app.
- [ ] Hosted publicly with **no login** (YouTube unlisted/public or a public Drive link).

**Slides**
- [ ] **≤ 7 slides including the title slide**; no hidden/backup slides.
- [ ] Slide 1 shows the team name, all member names and the challenge name.
- [ ] Public Google Slides link or PDF link, **no login**.

- [ ] Opened the demo link in a **private/incognito window**: it plays/loads without signing in.

## C. Links

- [ ] **Final project link:** https://lunascout.web.app opens in a private window with no login and runs the default analysis (status shows LIVE, not "Sample data").
- [ ] Source code link (https://github.com/lauta-r0/lunar-landing--) is **public** and opens in a private window.
- [ ] Custom domain (if used) resolves with HTTPS, and a **FortiGuard web-filter classification has been requested** for it (some school/corporate networks block uncategorised domains; request it early, it can take time). `[TO VERIFY]` the request page; not needed if only `lunascout.web.app` is used.
- [ ] Cloud Run service still has **min instances = 1** (no cold start for judges): `api/DEPLOY.md`. Smoke test passes: `powershell -File scripts/smoke_test.ps1 -BaseUrl https://lunascout.web.app`.
- [ ] Opened the app on a phone-width window; no horizontal scroll.

## D. Content rules

- [ ] **No NASA logos, insignia or mission patches** in the app, README, video, slides or form. (Credit NASA data in words only.)
- [ ] **No images, video or voice of anyone under 18** anywhere in our materials. Every voice/face is confirmed 18+.
- [ ] **AI-generated images/video carry a visible watermark.** (Best case: there are none. `project_page.md` says none are used; edit it if that changes.)
- [ ] **AI use is marked:** every AI-assisted code file starts with the header from CONTRACT §7, the README has a "Use of AI" section, and the form's "Use of Super Intelligence" field is truthful and matches what happened. The idea is the team's.
- [ ] No sample or made-up data is shown as real. The only sample data is `fixtures/sample_response.json`, behind the **SAMPLE DATA — API OFFLINE** badge.
- [ ] Athena wording is the validated one: *off target by a few hundred metres, tipped over in a ~20 m crater, mission ended about 12–13 h later.* **Never** "landed in shadow", "LunaScout would have predicted/saved Athena", or "validated against observations" (`docs/validation.md` §10).
- [ ] Numbers used are only those in `docs/validation.md` §10, our own app output, or cited sources. Fonts, libraries and data sources are listed with licences/attribution.
- [ ] README has the final screenshot (`docs/ui-desktop.png` is from an earlier build; retake it from the final deployment).
- [ ] Code licence decided and a `LICENSE` file added (MIT proposed).

## E. Submit

- [ ] Open the project in the Space Apps portal and fill the form from `project_page.md`.
- [ ] Tick **"Terms and Conditions"**. `[TO VERIFY]` exact label in the form.
- [ ] Tick **"Confirm All Work is Original"**. `[TO VERIFY]` exact label in the form.
- [ ] Click **"Submit for Judging"** (saving a draft is *not* submitting).
- [ ] **First submission by ~19:00** with the basic version, then improve.
- [ ] **Final submission before 23:00** (an hour of margin before 23:59). Reload the project page and confirm the status reads as submitted, with the last-saved time.
- [ ] Re-open every link from the submitted page in a private window one last time.

## F. After submitting

- [ ] Do not change the demo or app URLs after the final submit unless you resubmit.
- [ ] Keep the Cloud Run instance warm through judging; afterwards scale to zero or delete it to stop charges (`api/DEPLOY.md`, "After judging").
- [ ] Commit the final docs (README, `docs/submission/`, validation) to the repository so the public repo matches the submission.
