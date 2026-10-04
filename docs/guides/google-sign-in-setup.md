# Google Sign-In Setup

StyleSense signs users in with Google only. The backend verifies Google ID tokens against the **OAuth client IDs** you create here. Until at least one is configured, `POST /v1/auth/google` returns `503 sign_in_unavailable`.

It's free and takes about 15 minutes.

---

## 1. Create a Google Cloud project
1. Open https://console.cloud.google.com/ and sign in.
2. Top bar → project picker → **New project** → name it `stylesense` → **Create**.

## 2. Configure the OAuth consent screen
1. **APIs & Services → OAuth consent screen** (on newer consoles: **Google Auth Platform → Branding**).
2. User type: **External**.
3. Fill in the app name (StyleSense), support email and developer contact email.
4. Scopes: only the defaults (`openid`, `email`, `profile`). We need nothing else.
5. While testing, add your own Google account under **Test users**. Publish the app before the public launch.

## 3. Create the Web client (required, even for the Android app)
Android Google Sign-In issues ID tokens whose **audience is the Web client ID** (the app passes it as `webClientId`/`serverClientId`). So the Web client is the one the backend mostly sees.

1. **Credentials → Create credentials → OAuth client ID**.
2. Application type: **Web application**. Name: `stylesense-web`.
3. Authorized JavaScript origins: add your admin/public web origin later (e.g. `https://admin.<your-domain>`).
4. **Create** and copy the **Client ID** (ends in `.apps.googleusercontent.com`). The client secret isn't needed: we only verify ID tokens.

## 4. Create the Android client
This tells Google that tokens may be issued to *your* signed app.

1. **Create credentials → OAuth client ID → Android**.
2. Package name: the app's id (e.g. `app.stylesense`; we fix it in CP15).
3. **SHA-1 certificate fingerprint**:
   - Local/dev builds: `keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey -storepass android -keypass android`
   - Play Store builds: Play Console → your app → **Setup → App integrity → App signing** → copy the **App signing key** SHA-1. Add it as a *second* Android client.
4. **Create**.

## 5. (Later) iOS client
When we release on iOS: **OAuth client ID → iOS**, with the bundle id.

## 6. Configure the backend
In `.env` (JSON list; include every client whose tokens the backend should accept):

```
APP_GOOGLE_CLIENT_IDS=["<web-client-id>.apps.googleusercontent.com","<android-client-id>.apps.googleusercontent.com"]
APP_ADMIN_EMAILS=["you@gmail.com"]
```

Restart the stack (`make up`). Then:

```bash
curl -s -X POST localhost:8000/v1/auth/google -H 'content-type: application/json' -d '{"id_token":"x"}'
# → 401 invalid_id_token   (configured; the token is just fake)
```

`APP_ADMIN_EMAILS` gives those accounts the `admin` role at their next sign-in. Removing an email demotes it at the next sign-in or token refresh.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `503 sign_in_unavailable`, detail "not configured" | `APP_GOOGLE_CLIENT_IDS` is empty or not valid JSON |
| `503 sign_in_unavailable`, detail "could not reach Google" | The server can't reach `googleapis.com` (DNS/firewall) |
| `401 invalid_id_token` with a real token | The token's audience isn't in `APP_GOOGLE_CLIENT_IDS` (usually the Web client ID is missing), or the token expired (they last 1 hour) |
| `403 email_not_verified` | The Google account's email isn't verified |
| Sign-in works in dev but not from the Play Store | The Play **App signing** SHA-1 isn't registered as an Android client |
