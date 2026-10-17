# Publishing StyleSense on Google Play

What Google Play requires, what the app already does, and what is still to do before release.

## Already built into the app and server

| Requirement | Where |
|---|---|
| Privacy policy at a public URL | `/privacy` (text stored in `legal_documents`, versioned) |
| Account deletion in the app | Me → Privacy & account → **Delete account** (closed at once, data erased within 30 days) |
| Account deletion on the web, without the app | `/delete-account` |
| Terms of use | `/terms` |
| AI-generated content: users can report it | Try-on result → **Report this result** (hides it at once) |
| No sexual or abusive generated content | Chat guard refuses it; try-on refuses unusable or unsafe photos |
| Only the permissions we use | Camera and photo picker; microphone blocked (`app.json`) |
| Developer sign-in can't reach real users | Refused by the server in production |
| Signed release builds | EAS-managed keystore; `production` profile builds an Android App Bundle (`eas.json`) |
| Current target API level | Expo SDK 57 targets the Android version Play currently requires |

## To do before the first release

1. **Go live on a public HTTPS domain (CP19).** The privacy, terms and deletion URLs and the API must be reachable from the internet; `localhost` or Wi-Fi addresses are not accepted. Set `APP_PUBLIC_WEB_URL` and `APP_SUPPORT_EMAIL` (a real inbox you read).
2. **Play Console account** (one-time $25). New personal accounts must run a **closed test with at least 12 testers for 14 days in a row** before they can apply for production.
3. **Real Google sign-in only.** Make sure `APP_DEV_SIGN_IN_ENABLED` is off in production, and add the Play App Signing SHA-1 as a second Android OAuth client in Google Cloud (Play re-signs the app with its own key).
4. **Reviewer access.** In Play Console → App content → App access, give a test Google account that reviewers can sign in with.
5. **Store listing:**
   - app name (up to 30 characters), short description (up to 80), full description (up to 4,000);
   - a 512 × 512 icon, a 1024 × 500 feature graphic, and at least 2 phone screenshots;
   - category **Shopping**, plus the contact email and the privacy policy URL.
6. **App content forms:**
   - **Data safety** (see below).
   - **Content rating** questionnaire (IARC). Answer that the app includes AI-generated content and user-uploaded photos.
   - **Target audience: 13 and over**, not designed for children.
   - **Ads: none.** Mention the affiliate links in the description.
   - **Government apps, financial features, health:** none.
7. **Release build:** `npx eas-cli build -p android --profile production`, then upload the `.aab` to the closed testing track (or `eas submit`). Increase `version` in `app.json` for every release.

## Data safety answers

| Data | Collected | Shared | Purpose | Optional | Deletable |
|---|---|---|---|---|---|
| Name, email (Google account) | Yes | No | Account management | No | Yes |
| Photos (photo search, try-on) | Yes | With processors (Cloudinary, AI providers) | App functionality | Yes | Deleted within 24 h automatically |
| In-app messages to the stylist | Yes | With AI providers, without identity | App functionality, personalisation | Yes | Yes |
| App interactions (likes, saves) | Yes | No | Personalisation | Yes | Yes |
| Crash logs, diagnostics | Yes | No | App functionality | No | Yes |
| Device or other IDs (installation id) | Yes | No | App functionality, security | No | Yes |

- Data is **encrypted in transit**.
- People can **request deletion** in the app and on the web.
- No data is sold, and none is used for advertising.

## Policies to keep in mind

- **Generative AI:** keep the report button and keep refusing sexual, hateful or violent output.
- **User-generated content:** shared links and polls show products only, never personal data; reported content is hidden at once.
- **Affiliate links:** disclose them ("Store links may earn us a commission"); it's already on the sign-in screen and share pages.
