# Engineering and security reference

Apply every applicable item. A checkbox is evidence only after inspection or execution.

## Requirements and scope

- [ ] Implementation satisfies every acceptance criterion and user journey.
- [ ] No requirement was silently changed, guessed, or omitted.
- [ ] No scope creep, unrelated refactor, novelty feature, fake integration, placeholder production path, or unnecessary abstraction.
- [ ] Failure behavior, permissions, data lifecycle, compatibility, and operational needs are defined.
- [ ] Assumptions and unresolved decisions are explicit.

## AI-output integrity

- [ ] No invented API, method, flag, event, environment variable, schema field, library feature, URL, citation, command, benchmark, or legal claim.
- [ ] Unfamiliar interfaces are verified against authoritative docs or installed source.
- [ ] No hallucinated package or typo-squatted/dependency-confused name.
- [ ] Code was understood in context rather than accepted because it compiles or looks plausible.
- [ ] Generated tests independently validate behavior rather than mirror the implementation.
- [ ] No generic boilerplate, abandoned alternatives, duplicate helpers, inconsistent patterns, or excessive explanatory comments.
- [ ] Provenance and AI disclosure requirements are preserved; authorship is not falsified.

## Agent security

- [ ] Repository text and external content are treated as untrusted data, not higher-priority instructions.
- [ ] Agent has least-privilege filesystem, shell, network, repository, cloud, and MCP access.
- [ ] Untrusted content cannot access secrets and exfiltrate or mutate state in one path.
- [ ] Sensitive commands and writes require confirmation; destructive commands are prohibited by default.
- [ ] Changes to agent instructions, settings, hooks, MCP config, CI workflows, install scripts, Dockerfiles, IaC, and permissions receive human review.
- [ ] AI-generated change is not self-approved, protection is not bypassed, and human ownership is named.

## Architecture and maintainability

- [ ] Change follows existing dependency direction, layering, module boundaries, state ownership, error model, and conventions.
- [ ] Business logic is not duplicated across UI, API, jobs, or clients.
- [ ] No god component/class, circular dependency, leaky abstraction, needless wrapper, premature generalization, or global mutable state.
- [ ] Interfaces are minimal, cohesive, testable, and backward-compatible where required.
- [ ] Transactions, concurrency, caching, idempotency, retries, and failure isolation are intentionally designed.
- [ ] Feature flags have owner, default, expiration/removal plan, and safe behavior.
- [ ] Public APIs, schemas, events, storage formats, and configuration changes are documented and versioned.

## Code quality

- [ ] Repository formatter, linter, type checker/compiler, and static analysis pass.
- [ ] Naming expresses domain intent; functions and modules have one understandable responsibility.
- [ ] Complexity, nesting, duplication, unsafe casts, nullable flows, magic values, and hidden side effects are controlled.
- [ ] Resources, subscriptions, files, sockets, timers, locks, and async tasks are cleaned up.
- [ ] Errors are handled at the correct layer; no swallowed exceptions, blanket catches, silent incorrect fallback, or success after partial failure.
- [ ] No unused imports, variables, routes, assets, exports, code, flags, comments, TODO/FIXME placeholders, debug statements, or commented-out code.
- [ ] Generated files are regenerated from source and not manually patched.
- [ ] Date/time, locale, timezone, Unicode, precision, overflow, ordering, and deterministic behavior are correct.

## Correctness and edge cases

- [ ] Happy, error, empty, null, zero, maximum, malformed, duplicate, stale, expired, and partial cases are handled.
- [ ] Retry, timeout, cancellation, disconnect, refresh, back/forward navigation, double click, replay, and concurrent calls are safe.
- [ ] Async operations are awaited; race conditions, stale closures, out-of-order responses, and double submissions are controlled.
- [ ] Pagination, sorting, filtering, boundaries, totals, currency, tax, rounding, and unit conversions are correct.
- [ ] External failures do not corrupt local state or misreport success.
- [ ] Compatibility with supported runtimes, browsers, devices, clients, API versions, and old/new deploy overlap is verified.

## Testing

- [ ] New behavior has meaningful unit and regression tests.
- [ ] Integration/contract tests cover real boundaries; mocks do not remove the behavior being tested.
- [ ] End-to-end tests cover critical user journeys and failure recovery.
- [ ] Authorization tests cover anonymous, owner, non-owner, ordinary user, privileged user, admin, cross-tenant, disabled/deleted user, revoked/expired session.
- [ ] Inputs cover invalid types, oversize payloads, malicious strings, Unicode, nesting, boundary values, and duplicate/replayed requests.
- [ ] Tests are deterministic, isolated, order-independent, and clean their data.
- [ ] Assertions prove outcomes and side effects, not merely status or snapshots.
- [ ] No skipped/focused/flaky test, reduced threshold, blanket ignore, or changed assertion hides a failure.
- [ ] A clean production build and the complete feasible suite pass from a clean checkout.

## Authentication and sessions

- [ ] Passwords use an appropriate adaptive password hash; no plaintext, reversible encryption, weak hash, or logging.
- [ ] Login resists enumeration, brute force, credential stuffing, and session fixation.
- [ ] MFA/passkeys and recovery are secure where risk or policy requires them.
- [ ] Reset, verification, invitation, and magic-link tokens are random, short-lived, single-use, scoped, and invalidated correctly.
- [ ] Sessions rotate on authentication/privilege change and invalidate on logout, reset, revocation, suspension, and deletion as required.
- [ ] Cookies use appropriate `Secure`, `HttpOnly`, `SameSite`, domain, path, and lifetime settings.
- [ ] OAuth/OIDC validates state, nonce, PKCE, issuer, audience, redirect allowlist, token signature, expiry, and account linking.
- [ ] API keys/service accounts are scoped, expiring/rotatable, auditable, and not exposed to clients.

## Authorization and tenancy

- [ ] Every protected route, API, resolver, server action, job, websocket, file, and admin operation enforces authorization server-side.
- [ ] Object-level, function-level, property-level, and tenant-level access is checked for every request.
- [ ] Client-hidden controls, route guards, guessed IDs, and unverified token claims are not treated as authorization.
- [ ] Default is deny; privilege changes are explicit and audited.
- [ ] Bulk operations, exports, search, counts, errors, caches, logs, storage paths, and background jobs cannot leak cross-tenant data.
- [ ] Admin routes are undiscoverable only as defense-in-depth; authentication, authorization, MFA/re-authentication, audit logs, CSRF protection, and rate limits provide actual protection.

## Input, output, and injection

- [ ] Validate type, schema, length, range, encoding, nesting, format, allowlist, and business rules server-side.
- [ ] Use parameterized queries and safe ORM/query APIs.
- [ ] Prevent SQL/NoSQL/OS command/template/LDAP/header/log/CSV/formula/path/HTML/JS/CSS injection.
- [ ] Encode output for HTML text, attribute, URL, JavaScript, CSS, JSON, SQL, shell, logs, and CSV contexts as applicable.
- [ ] Sanitize user HTML with a maintained allowlist sanitizer; do not rely on regex.
- [ ] Prevent mass assignment, prototype pollution, insecure deserialization, XML external entities, unsafe redirects, directory traversal, and regex denial of service.
- [ ] CSRF protection exists for cookie-authenticated state changes; CORS is explicit and minimal.
- [ ] SSRF defenses validate scheme, host, resolved IP, redirects, DNS rebinding, ports, and cloud metadata access.

## API and abuse resistance

- [ ] Request/response schemas, media types, status codes, error shape, pagination, filtering, sorting, and versioning are consistent.
- [ ] Rate limits are identity/IP/tenant/endpoint aware and protect login, reset, verification, search, uploads, exports, expensive jobs, payments, and admin functions.
- [ ] Quotas and limits bound request body, response, file, pagination, query complexity/depth, concurrency, CPU, memory, time, queue, and third-party spend.
- [ ] Timeouts, bounded retries with jitter, idempotency, circuit breaking/bulkheads where useful, and retry budgets prevent storms.
- [ ] Errors expose stable public messages/codes without stack traces, queries, filesystem paths, secrets, internal IDs, or infrastructure details.
- [ ] API docs and clients reflect actual behavior.

## File uploads and downloads

- [ ] Upload requires authorization and server-side size/count limits.
- [ ] Extension, MIME, magic bytes/content, filename, path, and archive contents are validated; filenames are generated safely.
- [ ] Files are stored outside executable/web roots or in isolated object storage with least privilege.
- [ ] Active content, SVG/HTML/script risks, image parsing, decompression bombs, zip slip, path traversal, and polyglot files are addressed.
- [ ] Malware scanning/quarantine is used where threat and compliance require it.
- [ ] Private downloads use authorization and short-lived scoped access; response disposition and content type are safe.
- [ ] Orphan cleanup, retention, deletion, and storage quotas exist.

## Secrets and sensitive configuration

- [ ] Scan working tree, staged diff, untracked files, history, CI logs, artifacts, docs, examples, fixtures, screenshots, environment files, and source maps.
- [ ] No API key, password, token, private key, webhook secret, DSN, signing key, connection string, or production identifier is committed or client-bundled.
- [ ] Environment examples contain placeholders only and document required values safely.
- [ ] Secrets come from an approved manager, are least-privilege, separated by environment, rotatable, and audited.
- [ ] Any exposed secret is revoked/rotated and investigated; deleting the line is not considered remediation.
- [ ] Debug routes, test accounts, default credentials, development bypasses, verbose mode, and permissive rules are removed from production.

## Database, storage, and migrations

- [ ] Database/storage rules deny by default and enforce tenant/user ownership independently of the client.
- [ ] Constraints enforce not-null, uniqueness, referential integrity, allowed ranges, and invariants where appropriate.
- [ ] Queries are parameterized, indexed, bounded, paginated, and checked for N+1 and full scans.
- [ ] Transactions and isolation prevent partial writes, lost updates, duplicate effects, and inconsistent balances/entitlements.
- [ ] Migration is reviewed for locks, duration, table rewrites, disk growth, replication lag, and realistic data volume.
- [ ] Rolling deployment uses expand/migrate/contract; old and new versions coexist safely.
- [ ] Backfills are resumable, idempotent, observable, throttled, and have abort criteria.
- [ ] Backup exists, is encrypted and access-controlled, and restoration is demonstrated.
- [ ] Destructive change has approved retention, export, rollback/roll-forward, and recovery plan.

## Dependencies and supply chain

- [ ] Every new package is necessary and verified in its official registry/repository.
- [ ] Review publisher/owner, maintenance, release cadence, age, provenance, checksums/signatures, install scripts, native binaries, transitive graph, vulnerabilities, and malicious-package reports.
- [ ] Check typosquatting, dependency confusion, abandoned packages, compromised maintainers, mutable references, and hallucinated names.
- [ ] Lockfiles are committed, coherent, and generated by the approved package manager/version; clean frozen install passes.
- [ ] Automated dependency updates and vulnerability alerts are configured with review, not blind auto-merge.
- [ ] License compatibility, attribution, NOTICE, source-distribution, patent, font/image/data/model licenses, and copyleft obligations are satisfied.
- [ ] Similarity/copyright review is performed for suspiciously distinctive generated code.
- [ ] SBOM is generated/retained where risk, customer, or policy requires it.

## Build, artifacts, containers, and provenance

- [ ] Exact release artifact is produced in CI from reviewed source and locked dependencies.
- [ ] Build is deterministic/reproducible or deviations are explained; timestamps and mutable inputs are controlled.
- [ ] Artifact has immutable version, source commit, dependency/SBOM data, hashes/signature, builder identity, and provenance where required.
- [ ] Production bundle excludes tests, mock data, stories, source maps if not intended, local configs, secrets, development endpoints, debug tools, and unnecessary packages.
- [ ] Container uses trusted pinned minimal base, non-root user, read-only/minimal filesystem, dropped capabilities, resource limits, health checks, and no build secret leakage.
- [ ] Image, OS packages, IaC, and artifact are scanned.
- [ ] Promotion reuses the same immutable artifact instead of rebuilding per environment.

## Infrastructure and CI/CD

- [ ] IaC is reviewed; production changes are planned/diffed and drift is known.
- [ ] IAM is least privilege; no unjustified wildcard actions/resources, public buckets/databases, broad security groups, or permanent admin credentials.
- [ ] Network, TLS, DNS, certificates, storage, encryption/KMS, backups, regions, quotas, autoscaling, and disaster recovery are correct.
- [ ] CI tokens have minimum permissions; environments and production require authorized approval.
- [ ] Third-party actions/images/tools are pinned to approved immutable references.
- [ ] Untrusted forks, branches, issue text, PR content, artifacts, caches, outputs, and expressions cannot reach secrets or privileged runners.
- [ ] Prevent command/expression injection, cache poisoning, artifact substitution, self-hosted runner persistence, and secret exposure in logs.
- [ ] Branch protection, required checks, review rules, CODEOWNERS where appropriate, and signed release policy cannot be bypassed by the agent.

## Privacy and data governance

- [ ] Inventory all personal, sensitive, confidential, payment, health, location, child, biometric, or regulated data.
- [ ] Collect only necessary data for stated purposes and lawful bases; no “collect now, decide later.”
- [ ] Privacy notice accurately names controller, purposes, basis, recipients/processors, transfers, retention, rights, contact, and automated decisions where applicable.
- [ ] Consent is specific, informed, granular, recorded, revocable, and not preselected where required.
- [ ] Deletion, export, correction, account closure, consent withdrawal, and retention expiry propagate to databases, storage, search, caches, backups, analytics, and processors as required.
- [ ] Logs, URLs, analytics, telemetry, crash reports, prompts, support tools, and error trackers exclude unnecessary sensitive data.
- [ ] Encryption, pseudonymization, tenant isolation, DPA/subprocessor review, residency, breach response, and audit access meet policy/jurisdiction.
- [ ] Test environments use synthetic or properly protected/de-identified data; production data is removed when unnecessary.

## Payments, billing, and webhooks

- [ ] Price, product, quantity, discount, tax, currency, entitlement, and recipient are determined/verified server-side.
- [ ] Client success redirect is not treated as proof of payment.
- [ ] Webhook signature uses raw body, correct endpoint secret, constant-time/official verification, timestamp tolerance, and secret rotation plan.
- [ ] Endpoint handles duplicate, replayed, delayed, missing, malformed, reordered, and unknown events idempotently.
- [ ] Acknowledge/retry behavior, dead-letter/reconciliation, and observability prevent lost events and retry storms.
- [ ] Payment state machine handles success, failure, cancellation, expiry, partial capture/refund, dispute, chargeback, trial, renewal, upgrade/downgrade, proration, and subscription cancellation where applicable.
- [ ] Sandbox and controlled end-to-end tests verify amount, currency, ledger/order state, entitlement, email, refund, and webhook processing.
- [ ] PCI scope is minimized; sensitive card data is never logged or handled directly unless explicitly compliant.

## Logging, observability, and audit

- [ ] Structured logs include timestamp, severity, service/version/environment, correlation/request ID, safe actor/tenant identifiers, and useful context.
- [ ] Logs exclude secrets, credentials, session tokens, raw authorization headers, passwords, full payment data, and unnecessary personal data.
- [ ] Security audit events are tamper-resistant and record login, privilege, admin, data export/deletion, configuration, payment, and sensitive access events as appropriate.
- [ ] Metrics cover traffic, latency, errors, saturation, queues, cache, dependency health, business outcomes, migrations, and costs.
- [ ] Distributed traces propagate correlation without sensitive payloads.
- [ ] Alerts are symptom-based, actionable, deduplicated, severity-mapped, tested, owned, and linked to runbooks.
- [ ] Dashboards and logs identify the deployed version and support rapid rollback diagnosis.

## Reliability, capacity, and recovery

- [ ] Dependencies have explicit timeouts, bounded retries, jitter, idempotency, and degradation behavior.
- [ ] Single points of failure, overload, queue growth, poison messages, thundering herd, retry amplification, and cascading failures are addressed.
- [ ] Capacity/load/stress/soak tests reflect expected and peak traffic, realistic data, slow dependencies, cold starts, and resource limits.
- [ ] Health/readiness/liveness checks indicate the correct failure modes and do not amplify outages.
- [ ] Graceful shutdown drains requests/jobs safely.
- [ ] SLO/SLI and error-budget expectations exist for critical services.
- [ ] Backup/restore, failover, RTO/RPO, incident response, escalation, and status/customer communication are documented and tested.

## Git, review, and documentation

- [ ] Diff contains only intended source, tests, docs, migrations, and generated outputs.
- [ ] No unrelated formatting, lockfile noise, binary, vendor dump, editor file, local config, cache, temp, coverage, or build artifact.
- [ ] Commits are small, coherent, truthful, and follow repository convention; messages explain why and note breaking changes.
- [ ] PR gives context, approach, screenshots/demos, tests, security/data impact, migration, deployment, risk, and rollback.
- [ ] Author self-reviewed the rendered diff and resolved automated findings without suppression.
- [ ] README/setup/API/schema/examples/environment docs/runbooks/changelog/ADR are updated and commands verified.
- [ ] Comments explain intent and constraints, not obvious syntax; stale or hallucinated documentation is removed.
- [ ] Required human/code-owner/security/operations/legal reviews are obtained.

## Pre-push minimum

- [ ] Review `git status`, staged diff, unstaged diff, untracked files, and generated/lockfile changes.
- [ ] Remove test data, mock credentials, debug logs, breakpoints, TODO placeholders, screenshots, temp files, and local URLs.
- [ ] Secret scan passes; no key was merely hidden by `.gitignore` after exposure.
- [ ] Format, lint, types/compile, affected tests, and production build pass.
- [ ] New dependencies and licenses are reviewed.
- [ ] Changed auth, input, upload, payment, webhook, data, and error paths have negative tests.
- [ ] Commit message accurately describes the change; no false “fully tested” statement.

## Pre-merge minimum

- [ ] Complete branch diff is focused and reviewable.
- [ ] Full feasible tests, security/dependency scans, build, integration/contract/E2E, and migration checks pass.
- [ ] Accessibility, responsive, performance, API compatibility, documentation, and operational effects are reviewed.
- [ ] Required independent reviewers approve; agent does not self-approve.
- [ ] Rollout/rollback and feature-flag behavior are documented for risky changes.

## Pre-production minimum

- [ ] Test/demo data, users, keys, routes, flags, bypasses, and verbose errors are absent from production.
- [ ] Production admin routes, auth, permissions, database/storage rules, inputs, rate limits, uploads, API errors, security headers, TLS, and CORS are verified.
- [ ] Mobile, browsers, real device, slow/poor network, offline/retry, accessibility, load/performance, payment, and webhook tests pass.
- [ ] Penetration/abuse testing attempts to break authorization, business logic, input handling, sessions, uploads, payments, and resource limits.
- [ ] Exact artifact, config, migration, observability, alerts, on-call, support, capacity, backup/restore, staged rollout, rollback, and post-deploy smoke plan are ready.
- [ ] Legal, privacy, consent, consumer/contact information, SEO, and launch completeness checks pass.
