# Hosted beta threat model

The audit covers the hosted FastAPI entry point, GitHub OAuth, public repository ingestion, PostgreSQL job data and patch downloads. It uses the Codex Security threat-model workflow and inspects the local release candidate. Provider OAuth configuration and deployed infrastructure require their own verification.

## Assets and trust boundaries

- **User identity and report ownership.** GitHub supplies a numeric account ID. The OAuth result enters through one fixed callback with signed browser state and PKCE. The signed session is scoped to this host and mutations require the session CSRF value and the exact origin. The app checks the beta allowlist and queries records by both owner and ID. OAuth access tokens are used to retrieve the profile and are discarded. [Auth](../../src/mergerisk/hosted_auth.py) · [HTTP routes](../../src/mergerisk/hosted.py)
- **Repository fetch and analysis.** Repository URLs and branch names are untrusted request data. The service checks a strict GitHub URL form, builds an HTTPS GitHub remote, and fetches explicit refs into temporary storage. Parsed blobs and findings are treated as data. The hosted worker receives no database or OAuth secrets and the service exposes static analyses and patch downloads. [Ingestion](../../src/mergerisk/hosted_ingest.py)
- **Durable jobs and reports.** PostgreSQL is a trusted dependency reached through certificate-verified TLS. Queue admission and lease changes serialize in the database. Only the active lease can publish a result. Running work that loses its lease fails visibly and queued work remains available after a restart. A result can include source excerpts and a patch. The UI avoids injecting these values as HTML. [Storage](../../src/mergerisk/hosted_store.py) · [Browser rendering](../../src/mergerisk/static/hosted.js)
- **Deployment and secrets.** The web host, trusted Git distribution, GitHub and database provider are in the trusted computing base. The container uses a non-root UID. The public surface has an invite allowlist and bounded work admission. Runtime service secrets remain in provider configuration.

## Verification required

Test that user B cannot list, view, download or delete user A's run. Verify origin and CSRF enforcement, rejected OAuth state, secure cookie flags and login/logout. Test exact-byte patch application against the recorded candidate, limited or unavailable fetches, expired running work and report deletion. Verify live HTTPS, provider callback settings and on-host isolation before opening the beta. The public source restriction stays in effect until private-source access, revocation and retention have been separately verified.

Repository: MergeRisk
Version: 15f77ea plus the hosted beta working tree
