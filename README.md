# Tonight's Gig Song Request App

Minimal FastAPI app for live QR-code song requests at a gig. It uses:

- Python
- FastAPI
- SQLite
- Jinja2 templates
- simple CSS
- a tiny amount of vanilla JS for live dashboard refreshes

## Features

- Public landing page with performer name, Venmo tip button, request button, and Instagram link
- Public booking page with a contact-style form that can send email from the app
- Public song request form
- Simple success page after submitting a request
- Private password-protected performer dashboard
- Reverse-chronological request list with quick status buttons
- Live dashboard updates using WebSockets, with polling fallback
- QR code page and downloadable PNG that points to the public home page
- Admin gallery uploader for homepage gig photos, tucked into a collapsed drawer below the request list

## Files You Will Edit

Copy `.env.example` to `.env`, then edit these values:

- `PERFORMER_NAME`
- `ADMIN_PASSWORD`
- `VENMO_URL`
- `INSTAGRAM_URL`
- `SITE_TITLE`
- `BASE_URL`
- `BOOKING_EMAIL`
- `BOOKING_SUBJECT`
- `BOOKING_DELIVERY`
- `FORMSUBMIT_TARGET`
- `WEB3FORMS_ACCESS_KEY`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_EMAIL`
- `SMTP_USE_TLS`
- `SECRET_KEY` (optional but recommended)

`BASE_URL` is optional. If left blank, the app uses the current request host when generating QR links. Set it only if you want to force a custom public URL.

`DATA_DIR` is optional. Leave it blank locally. For hosted deployments that need SQLite and uploaded photos to persist, point it at a persistent disk mount such as `/var/data`.

## Quick Start

1. Create and activate a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   ```

2. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Create your env file:

   ```powershell
   Copy-Item .env.example .env
   ```

4. Edit `.env` with your performer details and links.

Fastest booking setup tonight: leave `BOOKING_DELIVERY=formsubmit`. The booking form will post directly to FormSubmit and send submissions to your inbox without using your Gmail SMTP account as the sender.

If you want to hide the raw destination email from the form action later, set `FORMSUBMIT_TARGET` to the random string FormSubmit emails you after activation.

Web3Forms is still supported with `BOOKING_DELIVERY=web3forms` plus `WEB3FORMS_ACCESS_KEY`, but some hosted free subdomains and TLDs can be blocked by their anti-abuse rules.

If you prefer SMTP instead, add your SMTP credentials to `.env`. For Gmail, use an App Password in `SMTP_PASSWORD`.

5. Run the app with uvicorn:

   ```powershell
   uvicorn app:app --reload
   ```

6. Open these pages:

- Public home: `http://127.0.0.1:8000/`
- Booking page: `http://127.0.0.1:8000/book`
- Request form: `http://127.0.0.1:8000/request`
- Admin login: `http://127.0.0.1:8000/admin/login`
- QR page: `http://127.0.0.1:8000/qr`

## How It Works

- SQLite database file is created automatically as `gig_requests.db`
- New public requests are inserted with status `New`
- Dashboard shows all requests in reverse chronological order
- Status buttons update requests to `New`, `Queued`, `Played`, or `Skipped`
- When a request changes, connected dashboards auto-refresh
- Booking form can send through FormSubmit, Web3Forms, or SMTP depending on configuration
- The newest uploaded gig photo becomes the full-screen background behind the home page action card

## Notes For Tonight

- This app does not verify payments
- Tip amounts are claimed tip amounts only
- There is no public screen mode
- There are no account features, scraping features, or chord tools

## Go Live Tonight

### Fastest hosted option if Render is blocked: Railway

This repo now includes [railway.toml](c:/Users/SeanGarry/Python%20Stuff/railway.toml) so Railway can deploy it directly from GitHub.

1. Go to Railway and create a new project from your GitHub repo.
2. Select this repo and deploy it.
3. After the service is created, attach a Volume to the service.
4. Set the volume mount path to `/data`.
5. In the service Networking settings, click `Generate Domain`.
6. Set these variables in Railway:
   - `ADMIN_PASSWORD`
   - `SMTP_PASSWORD`
   - `SECRET_KEY`
7. Open the generated domain and test:
   - `/`
   - `/request`
   - `/admin/login`
   - `/qr`

Railway automatically provides the app port, and the app will automatically use the attached Railway volume for SQLite data and uploaded photos.

### Best hosted option: Render

This repo now includes [render.yaml](c:/Users/SeanGarry/Python%20Stuff/render.yaml) and [.python-version](c:/Users/SeanGarry/Python%20Stuff/.python-version) so you can deploy it as a Render web service with a persistent disk for SQLite and photo uploads.

1. Push this project to GitHub.
2. In Render, create a new Blueprint from that repo.
3. Keep the web service on a paid plan with the attached disk. SQLite and uploaded gallery photos need persistent storage.
4. Fill in the secret values Render prompts for:
   - `ADMIN_PASSWORD`
   - `SECRET_KEY`
   - `SMTP_PASSWORD`
5. After the first deploy, open the service URL and test:
   - `/`
   - `/request`
   - `/admin/login`
   - `/qr`

Render will run:

```text
build: pip install -r requirements.txt
start: uvicorn app:app --host 0.0.0.0 --port $PORT
```

### Fastest one-night option: Cloudflare Quick Tunnel

If you want a public link from this laptop tonight without pushing to GitHub, install `cloudflared` on Windows and run:

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```

That gives you a random public `trycloudflare.com` URL you can use right away for your QR code.

## Run Command Summary

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app:app --reload
```
