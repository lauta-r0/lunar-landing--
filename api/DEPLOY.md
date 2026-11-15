# LunaScout API — deploy (Google Cloud Run)

- Project: `lunascout` · Region: `southamerica-east1` · Service: `lunascout-api`
- URL: https://lunascout-api-855190992553.southamerica-east1.run.app (public, no login)
- Config: 2 vCPU, 2 GiB, `--cpu-boost`, min instances 1, max instances 2, env `LUNASCOUT_THREADS=2`.
- Startup probe: HTTP `/api/health` on 8080, 5 s initial delay, every 5 s, 24 failures allowed (about 2 minutes).
  The port answers only after the engine has loaded (about 14 s locally), so the probe waits for it.

## How it is built
`Dockerfile` (python:3.12-slim, plus `libexpat1`, which rasterio needs) copies the runtime data into the image:
`data/raw/*.tif`, `data/derived/**`, `data/ephemeris/*.npz` (about 674 MB uploaded). That data is git-ignored, so
`.gcloudignore` exists to override gcloud's default of using `.gitignore` (which would drop `data/`). The data must be
present on the machine that runs the deploy.

## Deploy / redeploy (PowerShell, from the repo root `lunascout/`)
```powershell
gcloud run deploy lunascout-api --project lunascout --source . --region southamerica-east1 `
  --memory 2Gi --cpu 2 --cpu-boost --min-instances 1 --max-instances 2 `
  --allow-unauthenticated --set-env-vars LUNASCOUT_THREADS=2 `
  --startup-probe="httpGet.path=/api/health,httpGet.port=8080,initialDelaySeconds=5,periodSeconds=5,timeoutSeconds=3,failureThreshold=24"
```
Add `--set-env-vars ALLOWED_ORIGINS=https://your-frontend-origin` if the frontend is served from another origin.
Each deploy creates a new revision and routes 100% of traffic to it once it is healthy. Roll back by routing traffic to
an earlier revision: `gcloud run services update-traffic lunascout-api --project lunascout --region southamerica-east1 --to-revisions <REVISION>=100`
(list revisions with `gcloud run revisions list --service lunascout-api --project lunascout --region southamerica-east1`).
Logs: `gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=lunascout-api" --project lunascout --limit 50`.

## After judging: stop paying for the warm instance
```powershell
gcloud run services update lunascout-api --project lunascout --region southamerica-east1 --min-instances 0
```
With 0 the service scales to zero (the first request then waits for the ~15-30 s engine load). Set it back to 1 with
`--min-instances 1`. To remove everything: `gcloud run services delete lunascout-api --project lunascout --region southamerica-east1`.

## Estimated cost (approximate, not verified against the price list for this region; check the Google Cloud pricing calculator)
- Idle warm instance (min 1, 2 vCPU, 2 GiB): about US$1.2 per day, about US$36 per month. Worst case with 2 instances about US$2.5 per day.
- Per request compute is negligible (about 0.3-0.5 s of 2 vCPU). Cloud Build is within the free build minutes; Artifact Registry about US$0.1 per GB-month.
- Roughly under US$40 for 30 days against the US$300 free-trial credit; US$0 idle after `--min-instances 0`.

## Smoke test
```powershell
powershell -File scripts/smoke_test.ps1 -BaseUrl https://lunascout-api-855190992553.southamerica-east1.run.app
```
Output of the first deployed run (2026-11-15, from a Windows machine; "total" includes the network round trip to São Paulo):
```
[ OK ] health: 662 ms, schema 1.3
[ OK ] meta: 77 ms, 7 curated sites, default margin 0
[ OK ] analyze default first (cold or MISS): 1341 ms total, X-Cache MISS, X-Compute-Ms 506, P=0.445, verdict viable
[ OK ] analyze default repeat (HIT): 747 ms total, X-Cache HIT, X-Compute-Ms 0, P=0.445, verdict viable
[ OK ] analyze Athena actual site: 610 ms total, X-Cache MISS, X-Compute-Ms 260, P=0.88, verdict viable
[ OK ] out_of_coverage: HTTP 400, error out_of_coverage
[ OK ] 422 on bad input: HTTP 422
All checks passed
```
(An earlier run of the same script had `out_of_coverage` reported as failed because of a bug in the script's error-body reading, fixed since; the server answered correctly.)

## Not done yet
Firebase Hosting rewrite (`/api/**` to this service), custom domain, FortiGuard classification and a Cloud Monitoring uptime check on `/api/health` come with the frontend.
