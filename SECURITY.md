# Security Policy

## Scope and data classification

Bitcoin Accounting stores private financial records: transaction history, balances, wallet and exchange metadata, cost basis, tax reports, imports, audit records, integrity findings, and attestations. Treat its databases, exports, logs, uploads, backups, MCP output, and generated reports as sensitive financial data.

The application is bookkeeping software. It must never hold or request seed phrases, wallet backup words, private keys, signing keys, hardware-wallet PINs, or passphrases. In particular, the `wallets.seed_info` field is for non-secret descriptive metadata only.

## Secrets

Never commit or log:

- `.env` files or database URLs/passwords;
- web passphrases, session secrets, or session cookies;
- Bitcoin Core RPC cookies, RPC usernames, or RPC passwords;
- real exchange/wallet exports, database dumps, tax reports, or attestation bundles.

Use `.env.example` only as a template. Prefer Bitcoin Core cookie-file authentication over an explicit RPC username/password, keep the cookie readable only by the service account, and never expose Bitcoin RPC outside trusted local interfaces.

If a credential appears in a commit, issue, PR, chat, screenshot, log, or report, rotate/revoke it first. Removing it from a file or rewriting git history does not invalidate it.

## Deployment and authentication

1. Enable `BITCOIN_ACCOUNTING_AUTH_ENABLED=1` for any deployment reachable beyond localhost.
2. Set strong, unique values for `BITCOIN_ACCOUNTING_AUTH_PASSPHRASE` and `BITCOIN_ACCOUNTING_SESSION_SECRET`.
3. Terminate HTTPS at the reverse proxy or trusted tunnel and use secure cookies in HTTPS deployments.
4. Bind the app and database to the narrowest interface needed; prefer localhost plus Tailscale/nginx over public exposure.
5. Use a dedicated, least-privilege database account and restrict SQLite/database/backups to the service account.
6. Treat interactive API documentation and health details as internal in production.

Disabling application auth is a local-development convenience, not a safe production posture.

## Imports, exports, and MCP

- Validate import type and size, handle parser failures safely, and remove temporary files.
- Never commit fixtures derived from real financial exports unless they are irreversibly anonymized.
- Generated CSV, PDF, JSON, tax, and attestation artifacts remain sensitive after download; store and share them accordingly.
- The MCP server is read-only, but its treasury, transaction, cost-basis, and tax output is highly sensitive. Prefer local stdio access and authorize every connected AI/tool client.
- Do not copy secrets or unnecessary financial detail into AI prompts, tickets, or support bundles.

## Logging, backups, and retention

Logs and error responses must redact connection strings, passphrases, session tokens, RPC credentials, and imported row contents. Do not return stack traces or raw provider/database errors to remote clients.

Back up the database and any generated artifacts that are part of the accounting record. Encrypt off-host backups, restrict their permissions, test restoration periodically, and delete obsolete debug exports or local copies when no longer needed.

## Security-sensitive review checklist

- [ ] No real secrets, wallet exports, financial reports, or database dumps are committed.
- [ ] No seed phrase, private key, signing material, or hardware-wallet PIN is stored.
- [ ] Web auth remains enabled for non-local deployments.
- [ ] RPC stays local and credential material is redacted.
- [ ] MCP access remains local/authorized and read-only.
- [ ] Imports validate input and clean up temporary files.
- [ ] Before enabling PostgreSQL-backed tests, verify every `PG*` variable points to an isolated disposable test database; the current test suite does not enforce this guard automatically.
- [ ] Logs and API responses contain no financial records or credentials beyond what the caller explicitly requested.

## Incident response

1. Remove unintended public/network access.
2. Rotate affected database, web-session, or Bitcoin RPC credentials.
3. Invalidate active sessions and restart affected services.
4. Identify exposed reports, exports, backups, logs, and downstream copies.
5. Remove the secret from configuration/code and, if needed, clean git history after rotation.
6. Record the incident without repeating the secret or private financial content.

### Known incident tracking

A PostgreSQL credential was committed on 2026-01-28. The current-tree incident summary is being redacted by this change, but credential rotation and git-history/downstream-copy cleanup still require independent verification. That follow-up is tracked as Bug Base ticket `#143`. Do not copy the historical value into tickets, commits, or logs.

## Reporting a vulnerability

Do not open a public issue containing vulnerabilities, credentials, wallet details, or financial data. Report privately through a GitHub Security Advisory when available, or contact the repository owner privately. Include the affected path, reproduction steps, impact, and a redacted proof of concept.

There is no bug bounty program or guaranteed response SLA.
