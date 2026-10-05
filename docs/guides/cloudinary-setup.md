# Cloudinary setup (user photos)

StyleSense stores user photos (photo search, try-on selfies and results) in Cloudinary. The free plan is enough. Without it, photo search and try-on report "unavailable"; everything else works. Design: [ADR 0016](../adr/0016-cloudinary-for-media.md).

## 1. Account
Sign up at https://cloudinary.com/users/register_free (Free plan). Afterwards sign in at https://console.cloudinary.com.

## 2. Credentials → `.env`
Console → **Settings** (gear, bottom left) → **API Keys**. Copy:

| `.env` variable | Where |
|---|---|
| `APP_CLOUDINARY_CLOUD_NAME` | the **cloud name / product environment** id (e.g. `orenlkc0`), shown above the keys. Not the display name. |
| `APP_CLOUDINARY_API_KEY` | API Key (a number) |
| `APP_CLOUDINARY_API_SECRET` | API Secret (click the eye to reveal) |

Never commit or paste the secret anywhere but `.env`. If it leaks, regenerate it on the same page.

Check: `curl -u "$KEY:$SECRET" https://api.cloudinary.com/v1_1/$CLOUD/ping` → `{"status":"ok"}`. `cloud_name mismatch` means the cloud name is wrong.

## 3. Upload preset
Settings → **Upload** → **Add upload preset**:

| Field | Value |
|---|---|
| Name | `stylesense_user_uploads` (or set `APP_CLOUDINARY_UPLOAD_PRESET`) |
| Signing mode | Signed |
| Asset folder | `stylesense/uploads` |
| Use filename / Unique filename / Overwrite | Off / On / Off |
| Delivery type | Authenticated |
| Allowed formats | `jpg,png,webp,heic` |
| Incoming transformation | `c_limit,w_1600,h_1600/q_auto:good` (resizes and strips EXIF) |

## 4. Security
Settings → **Security**: turn **Strict transformations** on; keep unsigned uploading off.

## 5. Verify end to end
With the stack running: `docker compose ... exec api python -m stylesense.cli purge-media` should print `"ok": true`. To check the whole flow, upload a photo through the API and open its signed `url`.
