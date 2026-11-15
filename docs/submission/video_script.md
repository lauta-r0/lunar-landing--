<!-- Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team. -->
# LunaScout — 30-second demo video script

**Hard limit: 30.0 seconds.** Over the limit = not eligible for Global Judging. Aim for a final cut of **29 s** and check the exported file length (for example `ffprobe -v error -show_entries format=duration -of csv=p=0 video.mp4`).
The voice-over may be in Spanish; **English subtitles are mandatory** (`subtitles_en.srt`). On-screen text is English.
The alternative is the 7-slide deck in `slides_outline.md`; the team chooses on Sunday afternoon. Do not submit both as "the demo".

## 0. Decide first

| Decision | Recommendation |
|---|---|
| Hook wording | **Do not say Athena "landed in shadow".** Our validation shows its site was sunlit at terrain scale (LunaScout and LROC QuickMap agree); the loss came from tipping over in a ~20 m crater. The hook below only says what the sources support (off target, mission over within about a day). See `docs/validation.md` §10 ("Do not say"). |
| Tagline | Pick one of the 5 below (default: #1). |
| Voice | A team member (18 or older, confirmed), human voice. Avoid AI voices; if one is used, disclose it. |
| Language | Spanish VO + English subtitles is allowed. English VO needs no translation step and is the lower-risk option. |

### Taglines
1. **Plan for where you'll land, not where you aim.** *(default)*
2. Don't just check the target. Check the whole ellipse.
3. Every landing point, hour by hour.
4. Sun, Earth and terrain: will your lander survive where it really lands?
5. Slip the launch. Re-check the landing in seconds.

## 1. The demo scenario (real run, re-check before recording)

Use the app at https://lunascout.web.app with its defaults: landing **2027-10-12 14:00 UTC**, 7 days, ellipse 1000 × 600 m, azimuth 0, max darkness 50 h, max comms gap 72 h, min Earth 50 %, max slope 8°.

1. Type the target **−85.48962, 30.66935** ("Sunlit slope") into Latitude / Longitude → **Run analysis**. It is no longer a quick pick: since PR #15 the quick picks are Mons Mouton, VIPER Mission Area and Nobile Rim 1. Prefill the fields before the take and cut the typing, so the shot starts on the **Run analysis** click.
2. Result re-checked on 15 Nov 2026 through the live API (schema 1.6, same numbers as on 1.5): 66 viable / 27 risky / 280 not viable of 373 sampled points → **survival ≈ 18 %** (0.177), target verdict **not viable**. Recommended nearby: **1.0 km NE of target**, listed at 0.596 (+42 points).
3. Click the first recommendation → it re-runs at (−85.46624, 30.96435): **≈ 58 %** (0.575, 218 viable / 43 risky / 118 not viable), verdict **viable**, delay tolerance 8 days.

> Why not a quick pick: VIPER Mission Area (22.3 %, verdict viable) has a "1.0 km SW" card at 56 % whose re-run gives 42.9 %, and Nobile Rim 1 is 0 % on these defaults with no recommendation that helps the story. Sunlit slope keeps the clearest contrast (not viable 18 % → viable 58 %).
>
> `[TO VERIFY]` Numbers can move with a redeploy. **Record first, then write the voice-over numbers from what is on the screen** (and edit the subtitles to match). Note that the recommendation card shows a slightly different figure (59.6 %) from the re-run at that point (57.5 %) because the two evaluate different sample grids; use the re-run number on screen and say "about".

## 2. Shot-by-shot

Word budget: **≈ 2.5 words/second → 75 words for 30 s**. This script uses **64 English words** (see §3).

| # | Time | Visual | On-screen text (English) | Voice-over EN | Voice-over ES |
|---|---|---|---|---|---|
| 1 | 0:00–0:02 | Black title card, text fades in. No NASA logos. | **CD Band** · ORT Uruguay · NASA Space Apps 2026 — *Lunar Landing Site Navigator* | *(none, 0 words)* | *(ninguna)* |
| 2 | 0:02–0:05 | Slow zoom on a still of the south-pole terrain (our own hillshade from the app, not a NASA image). | **IM-2 "Athena" · March 2025** / A few hundred metres off target / Mission over within a day. Small print: *Hancock et al. 2026; SpacePolicyOnline* | "Athena landed off target. Mission over within a day." (9) | "Athena aterrizó desviada: misión terminada en un día." (8) |
| 3 | 0:05–0:10 | Cut to the app's header, then the full screen. | **LunaScout** / *Plan for where you'll land, not where you aim.* | "LunaScout. Plan for where you'll land, not where you aim." (10) | "LunaScout. Planifica dónde aterrizarás, no hacia dónde apuntas." (8) |
| 4a | 0:10–0:12 | Screen recording, 1080p: target −85.48962, 30.66935 already typed in, press **Run analysis**. | Enter a target and a landing ellipse | "Enter a target and ellipse." (5) | "Elige un objetivo y una elipse." (6) |
| 4b | 0:12–0:16 | The ellipse fills with green ● / amber ▲ / red ✕ points; hover one point to show its tooltip. | Every point, hour by hour | "LunaScout checks every point against real terrain and Sun and Earth positions." (12) | "LunaScout evalúa cada punto con relieve real y posiciones del Sol y la Tierra." (14) |
| 4c | 0:16–0:18 | **Zoom** on the survival number and the timeline (Sun vs. horizon). | **Survival ≈ 18 %** `[read from screen]` | "Survival: 18 percent." (3) | "Supervivencia: 18 %." (2) |
| 4d | 0:18–0:20 | Click the first recommended target; the map re-centres and the number jumps. | **1 km NE → ≈ 58 %** `[read from screen]` | "One kilometre northeast: 58 percent." (5) | "Un kilómetro al noreste: 58 %." (5) |
| 5 | 0:20–0:30 | 0:20–0:23: launch-delay chart (delay tolerance). 0:23–0:27: data footer / About modal showing JPL Horizons + LOLA. 0:27–0:30: end card. | "Launch slips? Re-check in seconds." → "Built on NASA data: JPL Horizons · LRO LOLA" → end card: **LunaScout** · lunascout.web.app · **CD Band** | "Launch slips? Re-check in seconds. Built on NASA data, LunaScout could help Artemis-era missions choose where, and when, to land." (20) | "¿La fecha se atrasa? Recalcula en segundos. Con datos de la NASA, LunaScout podría ayudar a misiones de la era Artemis a elegir dónde y cuándo aterrizar." (27) |

Notes on claims in the table:
- "Mission over within a day": about 12 h (Hancock et al. 2026) to about 13 h (SpacePolicyOnline). "A few hundred metres": 250 m (IM) to about 500 m (Hancock); the sources disagree, so the video does not give one number.
- "Real terrain": LRO LOLA topography (5 m/px near Mons Mouton, 20 m elsewhere). Do not say "5 m accurate" generally.
- "Could help … missions": LunaScout is a planning aid, not validated for operations. Do **not** say it "would have predicted" or "saved" Athena.
- "Re-check in seconds": server compute 240–440 ms in our 15 Nov check; end-to-end about 1–2 s. `[TO VERIFY]` on the final build.

## 3. Word budget check

| Segment | Seconds | EN words | EN words/s | ES words | ES words/s |
|---|---|---|---|---|---|
| 1 | 2 | 0 | 0.0 | 0 | 0.0 |
| 2 | 3 | 9 | 3.0 | 8 | 2.7 |
| 3 | 5 | 10 | 2.0 | 8 | 1.6 |
| 4 | 10 | 25 | 2.5 | 27 | 2.7 |
| 5 | 10 | 20 | 2.0 | 27 | 2.7 |
| **Total** | **30** | **64** | **2.1** | **70** | **2.3** |

Segment 2 is the tightest (3.0 words/s): read it briskly, or cut to the 7-word version "Athena landed off target. Lost within a day." (then change subtitle 1 to match) Spanish runs a little long; if the take exceeds 29 s, shorten segment 5 to "¿Se atrasa el lanzamiento? Recalcula en segundos. Con datos de la NASA, LunaScout ayuda a elegir dónde aterrizar." (and change the subtitle to match).

## 4. Full voice-over text (for the recording)

**English (64 words)**
> Athena landed off target. Mission over within a day.
> LunaScout. Plan for where you'll land, not where you aim.
> Enter a target and ellipse. LunaScout checks every point against real terrain and Sun and Earth positions. Survival: 18 percent. One kilometre northeast: 58 percent.
> Launch slips? Re-check in seconds. Built on NASA data, LunaScout could help Artemis-era missions choose where, and when, to land.

**Español (70 palabras)**
> Athena aterrizó desviada: misión terminada en un día.
> LunaScout. Planifica dónde aterrizarás, no hacia dónde apuntas.
> Elige un objetivo y una elipse. LunaScout evalúa cada punto con relieve real y posiciones del Sol y la Tierra. Supervivencia: 18 %. Un kilómetro al noreste: 58 %.
> ¿La fecha se atrasa? Recalcula en segundos. Con datos de la NASA, LunaScout podría ayudar a misiones de la era Artemis a elegir dónde y cuándo aterrizar.

Replace 18 / 58 with the numbers on screen when recorded.

## 5. Recording tips

- **Capture:** 1920×1080 screen capture, browser at 100 % zoom in a clean window (no bookmarks bar, no extra tabs, no notifications; turn on Do Not Disturb). Use the pinned-CDN page at https://lunascout.web.app, not a local build.
- **Warm up:** open the app and run the scenario once before recording, so fonts, the hillshade and the map are loaded and the result is cached. Record the take with a fresh click so the points still "light up".
- **Zoom on key numbers:** add a 1.3–1.5× zoom or highlight on the survival %, the timeline and the recommended-target card. Numbers must be readable on a phone.
- **No personal data on screen:** no email, account menu, file paths, other tabs or chats. Do not show the Google Cloud or Firebase consoles.
- **No minors** in any footage, voice, music or image. Confirm every voice and face is of someone 18 or older.
- **No NASA logos, insignia or mission patches** anywhere (including the end card). Credit NASA data in words only.
- **No AI-generated imagery.** If any is added, put a visible watermark on it.
- **Audio:** record the voice-over separately in a quiet room; use royalty-free music with a licence that allows this use, kept under the voice. `[TO VERIFY]` the music licence.
- **Subtitles:** burn in `subtitles_en.srt` (or upload it as a caption track) so they show for judges. Keep them inside the safe area, white text on a dark box.
- **Export:** MP4 (H.264), 1080p, ≤ 30.0 s. Upload as public/unlisted with no login (YouTube "Unlisted" or a public Drive link), then open it in a private window.

## 6. Source of each fact on screen

| Fact | Source |
|---|---|
| IM-2 off target by a few hundred metres (250 m IM; ~500 m Hancock) | https://spacepolicyonline.com/news/im-2-mission-ends-one-day-after-lunar-landing/ ; Hancock et al. 2026, doi:10.3847/PSJ/ae732f |
| Mission ended about 12–13 h after touchdown | Same two sources |
| Survival 18 % → 58 % | Our own live run, schema 1.6, 15 Nov 2026 (unchanged from 1.5); re-read from the screen when recording |
| Real terrain, Sun and Earth positions | LRO LOLA (NASA GSFC PGDA / PDS), JPL Horizons; `docs/validation.md` |
