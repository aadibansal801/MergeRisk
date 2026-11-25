# Hosted MergeRisk beta

The website runs on FastAPI and uses existing MergeRisk static analysis. Anyone with a GitHub account can sign in. The first successful sign-in creates a MergeRisk account. A user enters a public repository URL and two branch names, and receives findings about the recorded revisions. An exact, statically verified repair can be downloaded as a Git patch against the candidate merge tree. The local CLI and dashboard continue to use the local contract.

## Runtime and data

- One web process serves the UI and API and runs one analysis worker at a time. The GitHub fetch and analysis run in a disposable child process with service secrets excluded. Use Git 2.43 or newer. The Dockerfile checks Git during the build.
- The account table is created automatically on startup. It stores the numeric GitHub ID, current login, and creation time. Report ownership uses the numeric ID, so a username change preserves access to unexpired analyses. OAuth access tokens are used only to look up the GitHub profile.
- Accept public `https://github.com/owner/repo` URLs and explicit branches. Fetch only the requested histories. The hosted worker uses static analysis and a disposable Git index to verify exported patch bytes and discard its source workspace.
- Owner queries hide reports at 24 hours. The active worker checks for expired rows at least every minute when idle. Host sleep, database outages and provider backup retention can delay physical removal. The website also lets the owner delete completed runs. Treat patches and finding excerpts as source data. Keep request URLs, OAuth values, repository text and patches out of production logs.
- Admission is capped at one active job per user, four active jobs globally, five submissions per user per hour and fifty per day. A stopped running job becomes a visible failure after its lease expires. The user submits a new run if they want to compare the current branch tips. Queued jobs survive restarts.
- A free host can sleep or hit its quotas. The worker checks for pending work on startup and when users check or submit runs. Use a managed PostgreSQL endpoint with verified TLS, independent of instance disk.

## Configuration

The Docker image starts the hosted app on `$PORT` and exposes `/healthz`. Use `render.yaml` or a free Docker web service pointing at the verified deployment branch. Supply the following in the provider's environment settings.

- `MERGERISK_ORIGIN` is the exact HTTPS origin, without a trailing slash.
- `MERGERISK_DATABASE_URL` is a PostgreSQL connection string with `sslmode=verify-full`. Use the provider's CA path through `sslrootcert` when it is not trusted by the platform certificate store.
- `MERGERISK_GITHUB_CLIENT_ID` and `MERGERISK_GITHUB_CLIENT_SECRET` belong to a dedicated GitHub OAuth App. Set its callback to `<origin>/auth/github/callback`. Login uses PKCE and requests no repository scopes.
- `MERGERISK_SESSION_SECRET` is a random value of at least 32 bytes. Generate it in the deployment environment.

After deploy, confirm `/healthz`, then use a new GitHub account to sign in, run an analysis, and download the patch when available. Verify that signing in again restores access to the same unexpired reports. Check account isolation with a second account, then check queued and interrupted jobs across a restart. Record the exact release revision, failures and verified fixes. Private repository analysis requires a separate GitHub App authorization and retention review.
