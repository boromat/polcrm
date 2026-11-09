# Security policy

PolCRM keeps client data, finances and API keys of a small agency, and it can send parts of that
data to a language model. If you find a way to read or change data without logging in (or without
passing Cloudflare Access in that mode), to act beyond your role, to get a secret out of the
database in clear text, or to make the assistant send personal
data to the model while masking is on, please report it privately from the repository's
**Security** tab (*Report a vulnerability*) or write to kontaktboromat@gmail.com instead of
opening a public issue. You will get an answer within 7 days.

## What the app assumes

- It listens on `127.0.0.1` and is exposed through Cloudflare Tunnel or a reverse proxy with HTTPS.
- With `AUTH_MODE=password` (default) every page needs a login: scrypt hashes, rate limiting,
  sessions bound to the password, roles checked on the server. `/setup` works only until the first
  administrator exists - create it right after deploying (or use `scripts/create_admin.py`).
- With `AUTH_MODE=cloudflare` the identity comes only from the `Cf-Access-Authenticated-User-Email`
  header, checked against `ALLOWED_EMAILS`; the app must be reachable through the tunnel alone.
- `AUTH_MODE=profile` (no passwords) is a local demo mode and refuses to start in production.
- Secrets in the database are encrypted with Fernet; whoever has both the database and `.env` has
  the secrets.

## PII masking (polanon)

Masking is pseudonymisation, not anonymisation. It replaces what polanon detects (names, e-mails,
phone numbers, identifiers, company names with a legal form) and, always, the trade and legal
names of the agency's clients stored in the CRM, even when a client is named like a well-known
brand. A value nobody recognizes (for example a street name typed into a free-text note) is sent
as it is. When masking is switched on and polanon cannot run, the assistant sends nothing.
Detection gaps in polanon itself are best reported in the [polanon](https://github.com/boromat/polanon)
repository.
