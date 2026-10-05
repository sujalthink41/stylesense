# 0018 — Mobile foundation: Expo Go first, one design system, a thin GenUI renderer

**Status:** Accepted (2026-10-05)

## Context
The app must look the same and premium on Android and iOS, be testable on a phone from day one (Expo Go, no native build), and stay in step with a server that decides what each screen shows (GenUI, ADR 0011). Google sign-in needs OAuth client ids that don't exist yet.

## Decision
- **Expo SDK 57 + expo-router**, routes in `mobile/src/app`, guarded with `Stack.Protected` (update → sign-in → app). Only Expo Go-bundled native modules until a development build is needed (Google sign-in, push).
- **Developer sign-in for Expo Go.** `POST /v1/auth/dev {email}` issues a normal token pair; it exists only when `APP_DEV_SIGN_IN_ENABLED=true`, otherwise 404, and settings refuse it in production. The CLI `dev-token` shares the same code path.
- **Tokens:** the refresh token lives in SecureStore (Keystore/Keychain); the access token only in memory. A 401 triggers **one shared refresh** for all in-flight calls, then a single retry.
- **Design system "Indigo & Block"** in code, not a UI kit: tokens (`design/tokens.ts`), type (`design/typography.ts`, Anek Latin static instances cut from the variable font, OFL), atoms → molecules → organisms in `src/ui`. One custom look on both OSes; the system light/dark setting is followed.
- **GenUI renderer is a switch over generated types.** `scripts/gen-genui.mjs` compiles the backend's JSON Schema to `types.gen.ts`; `openapi-typescript` compiles `openapi.json` to `schema.gen.ts`. CI regenerates both and fails on any diff. Unknown component types render "Update StyleSense to see this." instead of crashing (the server also gates by `X-GenUI-Version`).
- **The stylist store is the only writer of a session:** one turn in flight, `stale_turn` → reload the snapshot, `session_busy` → one retry. Swipes go straight to `POST /v1/me/swipes` (ADR 0013); the deck refills locally and is keyed by turn, so a new server deck starts fresh and a refill only extends.
- **Crash reporting via `@sentry/react-native` pointed at our GlitchTip**, not Crashlytics: same self-hosted tool as the backend, no Firebase dependency yet. Off unless `EXPO_PUBLIC_SENTRY_DSN` is set; no PII.

## Consequences
- Google sign-in, push and the try-on camera need a development build (CP16/17); until then the dev sign-in is the way in, and only on non-production servers.
- Static font instances add ~1 MB but avoid variable-font rendering gaps on older Android.
- Contract drift between backend and app is caught in CI, not on a user's phone.
- npm audit reports highs inside Expo's build tooling (braces, node-forge, uuid@7) with no patched release; they don't ship in the bundle. CI gates on critical and the list is reviewed at each SDK bump.
