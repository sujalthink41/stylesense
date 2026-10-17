# Deploying StyleSense on a homelab server

This puts the backend on your own server. The internet reaches it through **Tailscale Funnel** (no domain needed) or a **Cloudflare Tunnel** (with your own domain):
- no router ports to open and no static IP;
- free HTTPS;
- works behind Jio/Airtel CGNAT.

Friends then install an APK that talks to `https://<your domain>`.

```
Phone ──HTTPS──► stylesense.yourdomain.com (Cloudflare) ──tunnel──► homelab
                                                                    ├─ tunnel (cloudflared)
                                                                    ├─ api   (FastAPI)
                                                                    ├─ worker (try-on, jobs)
                                                                    ├─ postgres + pgvector
                                                                    ├─ redis
                                                                    └─ backup (nightly pg_dump)
```

Nothing on the server listens on a public port. Share links (`/l/…`), poll pages (`/p/…`) and the privacy, terms and account-deletion pages are all served by the API on the same domain.

## 1. What you need

| Item | Notes |
|---|---|
| Server | Linux (Ubuntu 22.04+ or Debian 12), 64-bit, **4 GB RAM**, 20 GB free disk, always on |
| Docker | Docker Engine with the Compose plugin: `curl -fsSL https://get.docker.com \| sh`, then `sudo usermod -aG docker $USER` and log in again |
| Public address | Tailscale Funnel (free, no domain), or a domain on Cloudflare (about ₹800 a year) |
| Keys | The same ones as in your dev `.env`: Groq, OpenAI, Cloudinary, and the Google Web client ID |

Check Docker with `docker run --rm hello-world` and `docker compose version`.

## 2. Choose how the internet reaches the server

### Option A: Tailscale Funnel (no domain needed, free)

It gives you a permanent HTTPS address like `https://homelab.tail1234.ts.net`.

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up                # opens a login link: sign in with Google or GitHub
```

1. In the Tailscale admin console, under **DNS**, turn on **MagicDNS** and **HTTPS Certificates**.
2. Do the server install in step 3 below.
3. Then run:

```bash
sudo tailscale funnel --bg 8000  # the first time, it prints a link to allow Funnel: open it
tailscale funnel status          # shows your public URL
```

That URL is your `APP_PUBLIC_WEB_URL`. Leave `CLOUDFLARE_TUNNEL_TOKEN` empty.

### Option B: your own domain with a Cloudflare Tunnel

1. In the Cloudflare dashboard, go to **Zero Trust → Networks → Tunnels → Create a tunnel**, choose **Cloudflared**, and name it `stylesense`.
2. Copy only the **token** (the long string after `--token`). Docker runs cloudflared for you.
3. Add a **Public hostname**: `stylesense` on your domain → Service **HTTP**, URL `api:8000`.
4. Put the token in `CLOUDFLARE_TUNNEL_TOKEN`. `deploy.sh` then starts the tunnel container.

## 3. Install on the server

```bash
git clone https://github.com/sujalthink41/stylesense.git
cd stylesense
cp .env.prod.example .env
nano .env        # fill in every CHANGE-ME (see below)
./scripts/deploy.sh
```

What to put in `.env`:

| Setting | Value |
|---|---|
| `APP_PUBLIC_WEB_URL` | Your Funnel URL or `https://stylesense.yourdomain.com` (no trailing slash) |
| `APP_SUPPORT_EMAIL` | An inbox you actually read. It appears on the privacy and deletion pages. |
| `CLOUDFLARE_TUNNEL_TOKEN` | Empty for Tailscale; the token from step 2B for Cloudflare |
| `POSTGRES_PASSWORD` | `openssl rand -hex 24` |
| `APP_JWT_SECRET` | `openssl rand -base64 48`. Make a new one; don't reuse the dev secret. |
| `APP_GOOGLE_CLIENT_IDS` | `["<your Web client ID>"]`, the same ID as in `mobile/eas.json` |
| `APP_GROQ_API_KEY`, `APP_OPENAI_API_KEY`, `APP_CLOUDINARY_*` | Copy from your dev `.env` |

`deploy.sh` does the following:
1. Pulls `main`.
2. Backs up the database (when it already exists).
3. Builds the image.
4. Runs migrations; this also creates the privacy and terms pages.
5. Starts everything.
6. Sets the AI routes: text tasks on Groq, photos on OpenAI.

Check it worked:

```bash
make prod-ps                                        # all services Up / healthy
curl -s https://stylesense.yourdomain.com/readyz    # {"status":"ok",...}
```

Open `https://stylesense.yourdomain.com/privacy` in a browser. You should see the privacy policy with your support email.

The product catalog starts empty. Each new search fetches live results from Amazon.in, Flipkart and Myntra; the first search for a new item takes up to about 15 seconds.

## 4. Google sign-in for your friends

These settings are all in Google Cloud Console, under **APIs & Services**:

1. **OAuth consent screen.** While the app is in *Testing*, only the emails listed under *Test users* can sign in, up to 100. Either add each friend's Gmail address there, or click **Publish app**. Sign-in that only asks for email and profile doesn't need Google's review.
2. **Credentials.** Nothing new is needed for the APK. It's signed with the same EAS key whose SHA-1 you registered in the Android client. A Play Store build will need a second Android client, using the Play App Signing SHA-1.

## 5. Build the APK and share it

On your PC:

1. In `mobile/eas.json`, under the **preview** profile, set:
   ```json
   "EXPO_PUBLIC_API_URL": "https://stylesense.yourdomain.com"
   ```
2. Build:
   ```bash
   cd mobile
   npx eas-cli@latest build -p android --profile preview
   ```
3. When the build finishes (about 15 minutes), EAS shows a link and a QR code. Send the link to your friends.

When friends install it:
- On first install, Android asks to allow "Install unknown apps" for their browser or WhatsApp.
- Play Protect may warn that the app is unknown. Tap **More details → Install anyway**. This happens with any app installed outside the Play Store.

When you build a new APK, increase `version` in `app.json` (for example `0.1.1`) so it installs over the old one.

## 6. Day-to-day operations

| Task | Command (on the server, in `stylesense/`) |
|---|---|
| Update to the latest `main` | `make deploy` |
| Status | `make prod-ps` |
| Logs | `make prod-logs s=api` (or `worker`, `tunnel`) |
| Back up now | `make prod-backup` |
| Restore a backup (replaces all data) | `./scripts/restore.sh backups/stylesense-YYYYMMDD-HHMM.sql.gz` |
| Stop everything (data is kept) | `make prod-down` |

- **Backups:** a dump runs every night at 02:30 into `backups/`, and the last 7 days are kept. Copy that folder to another disk or cloud storage now and then; a backup on the same disk doesn't protect you if that disk dies.
- **Restarts:** every service restarts automatically after a crash or a reboot, as long as Docker starts on boot (`sudo systemctl enable docker`).

## 7. Costs while friends test

| What | Cost |
|---|---|
| Chat understanding and advice (Groq) | About ₹0.01 per message. Repeats are cached for 24 hours. |
| Photo search (OpenAI vision) | Under ₹1 per photo; 10 per person per day |
| Try-on (OpenAI images) | About ₹5–6 each. 3 per person per day and `APP_TRYON_GLOBAL_DAILY_LIMIT=30` for everyone, so at most about ₹180 a day. |
| Daily cap on all text AI | `APP_LLM_DAILY_BUDGET_USD=2.00`. When it's reached, the chat falls back to rules only. |

To change a limit, edit `.env` and run `make deploy`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Tunnel shows *Down* | Check `make prod-logs s=tunnel`. Usually the token is wrong; paste it again and run `make deploy`. |
| `502` / `Bad gateway` | The service URL in the tunnel's public hostname must be `http://api:8000`, not localhost. |
| API won't start: "google_client_ids is required" | Set `APP_GOOGLE_CLIENT_IDS` in `.env`. |
| Sign-in fails for a friend | Add them as a test user (step 4), or publish the consent screen. |
| App says it can't reach the server | Check the APK was built after you set `EXPO_PUBLIC_API_URL` in the preview profile. |
| Try-on says "studio is busy" | Your OpenAI credit has run out. Top it up; nothing else needs to change. |
