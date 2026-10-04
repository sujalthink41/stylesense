# 0006 — Authentication: Google ID tokens in, our own JWT + rotating refresh tokens out

**Status:** Accepted (2026-10-05)

## Context
Users sign in with Google only (no passwords, no OTP). We need fast request authentication, real logout, theft detection, role-based admin access and Play Store-compliant account deletion.

## Decision
- **Verify Google ID tokens locally** against Google's published keys (RS256 pinned, audience = our client IDs, issuer = Google, email must be verified). Users are keyed by Google's stable `sub`, not by email.
- **Issue our own tokens**: a 15-minute **HS256 access JWT** (`sub`, `sid` = session family, `role`) checked without a DB hit; and a 30-day **opaque refresh token**, stored only as a SHA-256 hash.
- **Rotation with reuse detection**: each refresh spends the token and issues a child in the same family. Reusing a spent token after a **30 s grace window** revokes the whole family. Within the window, parallel refreshes each get a sibling, so normal apps aren't logged out.
- **One session per app install** (`installation_id`): signing in again on the same install revokes the old session.
- **Admins** come from an email allow-list in config, re-checked on every sign-in and refresh.
- **Deletion**: `DELETE /v1/me` marks the account `deleting`, revokes all sessions and schedules a purge through the outbox after 30 days. Signing in to a deleting account is refused (`account_deleted`); restoring it is a support action.
- **JWT secret rotation**: tokens signed with `APP_JWT_PREVIOUS_SECRETS` still verify, so rotating the secret doesn't log everyone out.

## Consequences
- Request auth is a signature check: no DB or Redis round trip.
- A deleted or suspended user keeps a valid access token for at most 15 minutes, but `/me` and every refresh check account status.
- HS256 means only this backend can mint and verify tokens. If another service ever needs to verify them, switch to an asymmetric key (EdDSA) with a published JWKS.
