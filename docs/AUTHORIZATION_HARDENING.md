# Authorization hardening

## Private conversation ownership

Conversation threads are private by default. `conversation_threads` binds a
public `thread_id` immutably to its `project_id`, `owner_principal_id`, and a
server-generated `checkpoint_key`. The public thread identifier is never an
authorization credential and is not used as the protected Multi-Agent
checkpoint identifier.

Every public chat, resume, stream, memory-read, and memory-delete path first
requires a live project membership and then exact thread ownership. The
membership is read from PostgreSQL on every request, so revoking membership
immediately prevents both new messages and checkpoint resume. A
`platform_admin` claim does not bypass private-thread ownership; that policy is
intentionally unresolved and defaults to deny.

When LangGraph checkpointing is enabled, its namespace is derived only from the
server-generated `checkpoint_key`. The Multi-Agent runtime and its Knowledge
specialist handoff reject a request that lacks that key; they never fall back to
the client-provided `thread_id`. Stateless evaluation flows do not persist a
checkpoint.

Legacy LangGraph checkpoints without a matching ownership row cannot be
resumed. They must be explicitly migrated with a verified owner before access
can be restored. Shared conversations are intentionally not implemented;
future sharing requires an explicit scope and participant model.

## Implemented in this phase

- Production startup fails when `APP_ENV=production` (or `prod`) and `AUTHZ_ENABLED` is not true.
- Project creation inserts both the project and creator `admin` membership in one database transaction.
- Only project admins may list, grant, or revoke memberships. Revocation is effective immediately because every protected request reads the current membership at authorization time.
- Upload, processing, indexing, search, and RAG routes require an existing project. Background workers also reject missing projects rather than creating them implicitly.
- Task execution records persist the initiating `principal_id`, `project_id`, a safe `correlation_id`, and allowlisted route metadata.

## Required migrations

Run Alembic to revision `b7c3d9e1f2a4` before deploying this phase. It adds
the task-execution request context columns plus private conversation ownership.

### Rollback procedure for private-thread ownership

`b7c3d9e1f2a4` is deliberately **forward-only once ownership rows exist**.
Its Alembic downgrade refuses to drop `conversation_threads` while it contains
records; silently removing that table would turn protected checkpoints back
into unowned legacy checkpoints.

For an application rollback, deploy the prior application image only after a
documented decision that it will not serve private-thread endpoints, or restore
a verified database snapshot taken before this migration. Do not run an Alembic
downgrade against a database containing conversation ownership records. An
empty, disposable development database may downgrade normally.

## Explicitly unresolved policy decisions

These behaviors are unchanged and need product/security-owner approval before changing:

1. **`platform_admin` bypass:** whether an IdP-issued operational role may access every project without membership.
2. **Project creation policy:** which authenticated users may create projects.
3. **Last-admin protection:** the revocation API currently permits removing the last project admin. Decide whether to block it, require a replacement, or use a platform-admin recovery process.

## Deferred design decision

Tool authorization is deliberately not implemented in this phase. It requires
separate product and security decisions about capabilities, approval rules, and
service identities. Thread ownership is implemented as private-by-default;
future shared conversations require an explicit scope and participant model.
