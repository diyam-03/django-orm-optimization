# Deploying Query Lab on Render (free tier)

Render runs the web service and a managed PostgreSQL database. The repo includes `render.yaml`
(creates both) and `build.sh` (installs, collects static files, migrates, loads countries).

## 1. Push the project to GitHub
```
cd querylab
git init
git add .
git commit -m "Query Lab"
```
Create an empty repo on github.com, then:
```
git remote add origin https://github.com/<your-username>/querylab.git
git branch -M main
git push -u origin main
```
`.gitignore` already keeps `.env`, `.venv` and `staticfiles/` out.

## 2. Deploy with the Blueprint
1. Sign up at render.com and connect your GitHub account.
2. Click **New** then **Blueprint**, choose the `querylab` repo, and click **Apply**.
3. Render asks for `RESTCOUNTRIES_API_KEY`: paste your free key from restcountries.com/sign-up.
   (Without a key the build still works, but loads only the 30 sample countries.)
4. Render creates the `querylab-db` database and the `querylab` web service, then runs `build.sh`.
   Watch the build log; the first deploy takes a few minutes.
5. When the log says the service is live, open the `https://querylab-xxxx.onrender.com` URL
   shown at the top of the service page.

## 3. If you prefer to click everything yourself (no Blueprint)
1. **New, PostgreSQL**: name `querylab-db`, database `querylab`, plan Free. Wait until it is available,
   then copy its **Internal Database URL**.
2. **New, Web Service**: pick the repo. Runtime Python 3. Build command `./build.sh`.
   Start command `gunicorn querylab.wsgi:application`.
3. Environment variables:

| Key | Value |
|---|---|
| `DATABASE_URL` | the Internal Database URL from step 1 |
| `DJANGO_SECRET_KEY` | any long random string |
| `DJANGO_DEBUG` | `0` |
| `PYTHON_VERSION` | `3.12.3` |
| `DEMO_TOOLS` | `1` (or `0` to lock the data-changing buttons) |
| `RESTCOUNTRIES_API_KEY` | your key from restcountries.com/sign-up |

4. Create the service.

## 4. After it is live
- Open the URL. The page runs the comparison by itself.
- For the index demo, click **Add 200,000 test rows**, then **Run index benchmark**.
- Before the final demo or sharing the link widely, set `DEMO_TOOLS=0` in Environment so strangers
  cannot add rows or trigger benchmarks. The page then hides those buttons.
- Free web services sleep when idle, so the first visit after a while can take about a minute.
  Open the site a few minutes before presenting.
- Free Render databases have size limits and may expire. Check Render's current free-tier terms.

## Troubleshooting
| Problem | Fix |
|---|---|
| Build fails on `./build.sh: Permission denied` | run `git update-index --chmod=+x build.sh`, commit, push |
| `DisallowedHost` / 400 | add your domain to `EXTRA_HOSTS`; the `.onrender.com` name is automatic |
| Page has no styling | check the build log for `collectstatic`; WhiteNoise serves the files |
| `could not connect to server` | `DATABASE_URL` missing or wrong; use the Internal URL for the web service |
| Only 30 countries | the API call during build failed and the sample loaded; redeploy to retry |
