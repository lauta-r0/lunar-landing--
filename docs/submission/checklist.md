<!-- Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team. -->
# LunaScout — final pre-submission checklist

Deadline: **Sunday 15 Nov 2026, 23:59 local time (Uruguay, UTC−3)**. Plan: first "Submit for Judging" around **19:00**, final one before **23:00**. Resubmitting is allowed; **only the last saved submission counts.**

> **Source note.** This list is built from the brief the team gave us and from `CONTEXT.md` §8 / `00_PLAN.md`. The official Space Apps *Project Submission Guide* PDF was **not available** when this was written. `[TO VERIFY]` each item that says so against the guide before the final submit.

Tick each box only after you have checked it yourself.

## A. Team and form

- [ ] All 4 members are **confirmed on the team at the same Local Event** (Space Apps profile → team page). `[TO VERIFY]` in the guide whether every member must confirm.
- [ ] All required form fields are filled (project name, summary, demo link, final-project link, detailed description, SI use, NASA data, partner data/references). Text comes from `project_page.md`.
- [ ] Every placeholder is replaced (`[DEMO LINK]` is the only one left) and no `[TO VERIFY]` is left in anything submitted. Team: CD Band.
- [ ] The summary is about 150–200 words and the detailed description is 600–900 words (`project_page.md` has 199 and 900).
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
- [ ] README screenshots still match the final deployment. Retaken on 15 Nov 2026 from a local build of `develop` against the live API (schema 1.6), with the new quick picks: `docs/ui-desktop.png` (Sunlit slope typed in, 17.7 %), `docs/ui-best-sites.png` (VIPER Mission Area + Find best sites, 5 m only) and `docs/ui-mobile.png` (390 px). Retake them if the UI or numbers change again.
- [ ] **"Find best sites"** works on https://lunascout.web.app: heatmap and five ranked sites, labelled "Approximate"; clicking a site runs the full analysis. Checked through the API on 15 Nov 2026 (schema 1.6, defaults, all data): best site 79.5 % at −85.1436, 32.69785.
- [ ] **Quick picks** show exactly Mons Mouton, VIPER Mission Area and Nobile Rim 1, and each runs. Nobile Rim 1 gives **0 %** on the default settings; that is a real result, not an error.
- [ ] **Athena by hand** (it is no longer a quick pick): latitude −84.79059, longitude 29.19567, landing 2025-03-06 17:28 UTC (the analysis rounds to 17:00), 10 days → about **92.7 % viable** on 20 m data (live, 15 Nov 2026). Say why it shows viable (`docs/athena_replay.md`): the ~20 m crater is below the data resolution and the lander is assumed upright.
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
