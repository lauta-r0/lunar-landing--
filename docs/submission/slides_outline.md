<!-- Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team. -->
# LunaScout — 7-slide deck outline (fallback to the video)

**Hard limit: 7 slides including the title slide.** More than 7 = not eligible for Global Judging. Slides must be **in English**. The guide requires the **team name, member names and the challenge** to appear (slide 1). Max ~25 words of text per slide; the on-slide word count is shown for each. Export as PDF or a public Google Slides link (no login) and open it in a private window.

Rules for every slide: no NASA logos, insignia or mission patches; credit NASA data in words only; no photos of anyone under 18; screenshots are of our own app; AI-generated images get a visible watermark (use none if possible). Use the app's palette (dark background; Sun yellow `#FFE066`, Earth blue `#8CC4FF`, viable green `#3DDC84`, risky orange `#FF9F43`, not viable red `#FF6B6B`) and the Barlow font so the deck matches the product.

Numbers marked `[TO VERIFY]` must be read from the live app / `docs/validation.md` on the day.

---

### Slide 1 — Title
**Text (21 words):**
LunaScout. Plan where you'll land.
Team CD Band: Lautaro Montes, Agustin Guerequiz, Francisco Castelli, Sebastián Luciardi.
Challenge: Lunar Landing Site Navigator.
**Visual:** full-bleed crop of the app's polar-stereographic hillshade with the green/amber/red ellipse glowing in the centre; wordmark "LUNASCOUT" top-left (text only, no logo from NASA).

### Slide 2 — The problem
**Text (25 words):**
Landers miss targets. At the pole, a few hundred metres can mean sun or shadow. IM-2 Athena, 2025: off target, mission over in a day.
**Visual:** one simple diagram: a target dot, a dashed ellipse around it, an arrow to a different landing dot, and a Sun at 2° above a ridge. Small-print source line: Hancock et al. 2026; SpacePolicyOnline. *Do not draw Athena in shadow.*

### Slide 3 — The solution
**Text (20 words):**
LunaScout evaluates the whole landing ellipse, not one point: survival probability, launch-delay tolerance, better nearby targets and the best sites region-wide.
**Visual:** four outputs side by side (cut from the app): the survival % ring, the delay-tolerance curve, the "Recommended nearby" card and the best-sites heatmap with its ranked pins (`docs/ui-best-sites.png`; label it "Approximate").

### Slide 4 — How it works + NASA data
**Text (24 words):**
1 LOLA terrain. 2 Horizon at every point. 3 Sun and Earth from JPL Horizons. 4 Hourly simulation. 5 Viable, risky or not viable.
**Visual:** a 5-step horizontal flow (same as the README diagram) with two small labels under it: "NASA LRO LOLA 5/20/40 m DEMs" and "NASA JPL Horizons, hourly 2025–2028".

### Slide 5 — The experience
**Text (24 words):**
Enter target, date, ellipse and limits. Points turn green, amber or red. At this target, survival is about 18%; one kilometre northeast, about 58%.
**Visual:** a full-width, cropped screenshot of the real app showing the ellipse, the survival number and the timeline, with two callouts on the two numbers. `[TO VERIFY]` numbers (re-read from the screen; see `video_script.md` §1). Show the "Sample data" badge **only** if the screenshot is of the offline fixture, which it should not be.

### Slide 6 — Validation
**Text (21 words):**
Sunlight agrees with LROC QuickMap on 95–98% of about 3,000 points per date. Sun and Earth match JPL Horizons within 0.002°.
**Visual:** one of the QuickMap comparison figures (`docs/validation/quickmap_vs_lunascout_2027-10-12.png`) beside a small table of the three dates (98.0 / 95.5 / 96.8 %). Footnote: QuickMap shadows are a model, not observations.

### Slide 7 — Impact and future
**Text (24 words):**
Faster re-planning when launches slip. Next: more south-pole regions, relay satellites, a thermal model. A planning aid for Artemis-era missions, not an operational tool.
**Visual:** the app's launch-delay curve, with the line "Launch slips? Re-check in seconds." underneath. End with the live URL: lunascout.web.app.

---

## Checks before exporting
- 7 slides exactly (title counts). No hidden or backup slides.
- Slide 1 shows the team name, all four member names and the challenge name.
- English only; spell-check; the numbers on slides 5 and 6 match the app and `docs/validation.md`.
- No claim that LunaScout "would have predicted/saved Athena", that Athena "landed in shadow", or that it is "accurate to 5 m" (the 5 m resolution applies only on the Mons Mouton tile).
- Public link tested in a private window.
