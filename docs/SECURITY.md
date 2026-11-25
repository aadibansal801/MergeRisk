# Security model

Source is data. Default analysis does not import modules, load plugins, run tests, invoke a shell or execute project hooks/drivers. Git is a trusted installed dependency selected from absolute PATH entries outside the checkout. Argument arrays, bounded input/output and timeouts are enforced. Operational Git commands ignore global and system configuration, inherited redirection, lazy fetch and remote transports. Author identity alone is read as data from normal config. Hooks, signing, fsmonitor, merge drivers, renormalization and replace-object redirection are disabled.

Paths are normalized repository-relative values. Traversal, .git aliases, drive/alternate-stream separators, control separators and backslash escapes are rejected. Symlink/submodule source payloads are never followed. Registration rejects directory symlinks/junctions and rechecks canonical roots. Preview reads object bytes instead of materializing worktrees.

## Repairs and Git writes

Hashes bind byte edits to the inspected source/tree. Only history-backed mechanical sites are AUTO. AST whitelists are additional guards, not general semantic equivalence proofs.

Preview may create unreachable merge objects but never changes refs/index/checkout. Explicit artifact creation writes objects and a unique artifact ref. Explicit apply requires exact left HEAD, a completely clean checkout, regular-file trees and no external checkout filters. Git's prepared transaction holds branch/HEAD locks while checked read-tree and ref commit run. Competing ref writers are rejected. Ref failure attempts a checked reverse checkout before aborting.

Worktree updates are not a filesystem-wide atomic transaction. Do not edit or run checkout operations concurrently. Disk failure/hostile editors may require manual inspection; safe rollback failure is reported and unique work is never force-reset. Abrupt termination can leave normal Git locks; inspect processes/reflog before removing a stale lock yourself. Reftable/unknown lock arrangements, overwrite recovery and force-push are unsupported.

## Dashboard

The only bind is 127.0.0.1, with proxy headers disabled. Host and same-origin checks guard rebinding and cross-origin requests. The launcher prints a private link that exchanges a random access token for a per-process HTTP-only SameSite=Strict session. Access logs are disabled and the browser redirects to the token-free URL. Mutations also require a CSRF header and a JSON body capped at 16 KiB. Keep the launcher link private and keep the dashboard within the trusted local user environment.

Jinja escapes source, filenames, branches, errors and logs. JavaScript uses textContent and DOM options for untrusted text. CSP forbids external scripts, inline handlers, objects and framing. Registered IDs constrain access. Fingerprints and result versions reject stale/double actions. A process lock prevents two servers using one store.

One worker and three queued jobs bound concurrency. Cancellation checks occur between phases. Current Git commands finish or time out. History admission stops at 500 runs or 256 MiB of live SQLite pages. Admitted jobs can still add results. Snapshot limits include 10,000 entries, 2 MiB per blob, 32 MiB per batch, and 64 MiB of logical Python source across the four versions. Subprocess output is capped at 64 MiB. Limit failures never become clean results.

History and exports contain source snapshots. Protect them like repositories. POSIX history databases and sidecars use owner-only permissions. On Windows, use the default user-profile state path or a directory with equivalent Windows access controls. The local dashboard has no source upload, telemetry or third-party asset fetch.

## Runtime runner

Only explicit immutable locally installed image IDs without declared volumes are accepted. The runner has no pull or host fallback. Each container sees a temporary read-only tracked snapshot mounted from inside a private directory. The snapshot excludes `.git` and preserves tracked files, so keep credentials out of tracked repository contents. Each snapshot is capped at 32 MiB across paths. UID/GID 65534, dropped capabilities, no-new-privileges, a read-only root, capped tmpfs, CPU, memory, processes, time and output, and explicit cleanup constrain the run.

Isolation depends on trusted Docker/image/platform and is not VM-grade containment against container escapes. Parent/environment failures and absent infrastructure do not pass. The daemon was absent here; command construction/cleanup were tested, actual containers were not.
