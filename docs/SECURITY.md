# Security model

Source is data. Default analysis does not import modules, load plugins, run tests, invoke a shell or execute project hooks/drivers. Git is a trusted installed dependency. Argument arrays, bounded input/output and timeouts are enforced. Operational Git commands ignore global/system configuration and inherited redirection; author identity alone is read as data from normal config. Hooks, signing, fsmonitor, merge drivers/renormalization and replace-object redirection are disabled.

Paths are normalized repository-relative values. Traversal, .git aliases, drive/alternate-stream separators, control separators and backslash escapes are rejected. Symlink/submodule source payloads are never followed. Registration rejects directory symlinks/junctions and rechecks canonical roots. Preview reads object bytes instead of materializing worktrees.

## Repairs and Git writes

Hashes bind byte edits to the inspected source/tree. Only history-backed mechanical sites are AUTO. AST whitelists are additional guards, not general semantic equivalence proofs.

Preview may create unreachable merge objects but never changes refs/index/checkout. Explicit artifact creation writes objects and a unique artifact ref. Explicit apply requires exact left HEAD, a completely clean checkout, regular-file trees and no external checkout filters. Git's prepared transaction holds branch/HEAD locks while checked read-tree and ref commit run. Competing ref writers are rejected. Ref failure attempts a checked reverse checkout before aborting.

Worktree updates are not a filesystem-wide atomic transaction. Do not edit or run checkout operations concurrently. Disk failure/hostile editors may require manual inspection; safe rollback failure is reported and unique work is never force-reset. Abrupt termination can leave normal Git locks; inspect processes/reflog before removing a stale lock yourself. Reftable/unknown lock arrangements, overwrite recovery and force-push are unsupported.

## Dashboard

The only bind is 127.0.0.1; proxy headers are disabled. Host/same-origin checks guard rebinding and cross-origin requests. APIs require a per-process random HTTP-only SameSite=Strict session; mutations also require a CSRF header and JSON body capped at 16 KiB. No wildcard CORS or public mode exists. This is a same-user local application, not a boundary against malware running as the same OS account.

Jinja escapes source, filenames, branches, errors and logs. JavaScript uses textContent and DOM options for untrusted text. CSP forbids external scripts, inline handlers, objects and framing. Registered IDs constrain access. Fingerprints and result versions reject stale/double actions. A process lock prevents two servers using one store.

One worker/three queued jobs bounds concurrency. Cancellation checks occur between phases; current Git commands finish or time out. History admission stops at 500 runs/256 MiB of live SQLite pages; admitted jobs can still add results. Snapshot limits: 10,000 entries, 2 MiB/blob, 32 MiB/batch, 64 MiB unique four-version source. Subprocess output is capped at 64 MiB. Limit failures never become clean results.

History/exports contain source snapshots. Protect them like repositories. There is no source upload, telemetry or third-party asset fetch.

## Runtime runner

Only explicit immutable locally installed image IDs are accepted; no pull or host fallback. Each container sees a temporary read-only tracked snapshot without .git, secrets, privileged mounts or network. UID/GID 65534, dropped capabilities, no-new-privileges, read-only root, capped tmpfs/CPU/memory/processes/time/output and explicit cleanup constrain it.

Isolation depends on trusted Docker/image/platform and is not VM-grade containment against container escapes. Parent/environment failures and absent infrastructure do not pass. The daemon was absent here; command construction/cleanup were tested, actual containers were not.
