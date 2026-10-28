# Changelog

All notable changes to this project will be documented in this file. Versions
follow [semantic versioning](https://semver.org); 0.2.0 is the first release
published to PyPI, 0.1.0 is the first tagged release, and 0.0.1 is the
development baseline.

---

## [0.5.0] - Unreleased

0.5.0 brings further community contributions, API coverage checks that find
missing endpoints and drift on their own, and hardened write and tool
contracts. It also prepares the server for OpenProject 18 and makes it easier
to install and discover.

### Added

- `update_work_package_comment` previews and confirms replacement of an existing
  comment, including permission checks and warnings about notifications and
  irreversible text replacement.
- List and upload attachments on wiki pages, forum posts, meetings and comments.
- List available assignees and relation candidates for work packages.
- Opt-in `extended` tools list a project's budgets, the projects a version is
  shared with, the users that can watch a work package, the projects it can
  move to and its repository revisions, limited to
  `OPENPROJECT_READ_PROJECTS`; `OPENPROJECT_HIDE_BUDGET_FIELDS` and
  `OPENPROJECT_HIDE_REVISION_FIELDS` hide their fields.
- `get_notification` reads one notification with its details and activity, and
  `mark_notifications_unread` marks one or all read notifications unread.
- `set_query_starred` stars or unstars a saved query; a public query needs its
  project in `OPENPROJECT_WRITE_PROJECTS`, or the write scope `*` without one.
- `select` on `bulk_create_work_packages` and `bulk_update_work_packages`
  picks fields of each written work package as `result.<field>`, e.g.
  `["work_package_id", "result.status"]`; a bare work package field name is
  rejected with the path to use.
- `doctor` now reports the Python version and executable in use, warns when a
  client configuration file with an OpenProject entry has unsafe
  group/other-readable permissions (POSIX only), and checks in-process, with a
  time limit, that the server builds and dispatches tool calls. API
  connectivity failures now distinguish TLS/certificate errors from a plain
  connection failure and include actionable remediation hints.
- Optional structured stderr logging of per-tool-call diagnostics
  (`OPENPROJECT_LOG_FORMAT=json`), one JSON line per call carrying the tool
  name, outcome, duration, error code/layer, HTTP request count (accurate
  across retries), project scope, policy decision, and MCP request ID. A
  successful call logs at `INFO`; set `OPENPROJECT_LOG_LEVEL=INFO` too (the
  default is `WARNING`) to see those lines, not just failures. Written to
  stderr only, never stdout, which stays reserved for MCP JSON-RPC traffic.
  Off by default (`text` format, unchanged output); never logs the API
  token, Authorization header, work-package bodies, attachments, or other
  request/response payload content.
- `list_meetings` accepts a `title` filter (case-insensitive substring,
  also matching a recurring series' title) on OpenProject 17.9 and later.
- `end_recurring_meeting` ends a recurring meeting series and deletes its
  already created future occurrences; the series and its past occurrences are
  kept (OpenProject 17.8 and later).
- Work packages expose `observed_in_versions` (OpenProject 17.9+): read on
  every work package, written through the create, update and bulk tools, and
  filterable with `list_work_packages(observed_in_version=...)`. It follows the
  rules of the other version fields: a version defined outside
  `OPENPROJECT_READ_PROJECTS` is not named and an update that would remove one
  is refused, and a hidden field cannot be used to filter, sort or group.

### Changed

- A rejected status change on `update_work_package` and
  `bulk_update_work_packages` now lists, in its `status` validation error, the
  status values OpenProject's update form offers for that work package,
  including its current status.
- A confirmed bulk write no longer returns an item's echoed `payload` when
  `select` names it; the normalized `result` carries the same data.
- **Breaking:** Python 3.11 or later is required; Python 3.10 is no longer
  supported. Install or upgrade under Python 3.11+ (for example
  `pipx install --python python3.11 openproject-ce-mcp`).
- **Breaking:** tool error messages now carry a small, stable set of
  uppercase agent-facing codes (`AUTHENTICATION_FAILED`, `PROJECT_SCOPE_DENIED`,
  `CAPABILITY_DISABLED`, `OPENPROJECT_PERMISSION_DENIED`, `RESOURCE_NOT_FOUND`,
  `VALIDATION_FAILED`, `CONFLICT`, `RATE_LIMITED`, `OPENPROJECT_UNAVAILABLE`,
  `NETWORK_ERROR`, `CONFIGURATION_ERROR`, `INTERNAL_ERROR`) instead of the
  previous lowercase categories (`validation_error`, `auth_error`,
  `permission_denied`, `not_found`, `transport_error`, `server_error`,
  `configuration_error`, `openproject_error`). A
  caller matching on the old `[category]` prefixes must update to the new
  codes. Three distinctions that were previously conflated are now separate:
  a project outside `OPENPROJECT_READ_PROJECTS`/`OPENPROJECT_WRITE_PROJECTS`
  (`PROJECT_SCOPE_DENIED`) is no longer the same code as an `OPENPROJECT_ENABLE_*`
  capability flag being off (`CAPABILITY_DISABLED`) or OpenProject's own 403
  (`OPENPROJECT_PERMISSION_DENIED`); OpenProject's `409 Conflict` (e.g. an
  optimistic-locking version mismatch) no longer reports as `VALIDATION_FAILED`;
  and `429 Too Many Requests` no longer reports as `OPENPROJECT_UNAVAILABLE`.
  Any unexpected internal error is now sanitized to a generic
  `[INTERNAL_ERROR] An internal error occurred.` rather than leaking the raw
  exception message.

### Removed

- **Breaking:** `OPENPROJECT_ALLOWED_PROJECTS`/`_READ`/`_WRITE` no longer emit
  a startup/`doctor` deprecation warning or get prefilled by `configure`.
  These names have had no effect on the running server since 0.3.0; use
  `OPENPROJECT_READ_PROJECTS`/`OPENPROJECT_WRITE_PROJECTS`.

Thanks to our contributor: [@feci](https://github.com/feci) ([#35](https://github.com/jtauschl/openproject-ce-mcp/pull/35), [#36](https://github.com/jtauschl/openproject-ce-mcp/pull/36), [#43](https://github.com/jtauschl/openproject-ce-mcp/pull/43), [#44](https://github.com/jtauschl/openproject-ce-mcp/pull/44)).

## [0.4.4] - Unreleased

### Security

- The package requires `certifi` 2026.10.18 or newer: older bundles trust emSign
  roots whose intermediate keys are compromised, and `httpx` verifies the TLS
  connection to OpenProject against that bundle. Upgrade with `uv tool upgrade
  openproject-ce-mcp` or `pip install -U openproject-ce-mcp`.

## [0.4.3] - 2026-10-28

### Security

- A work package field hidden with `OPENPROJECT_HIDE_WORK_PACKAGE_FIELDS` could
  still be read through a query. `list_work_packages` and `search_work_packages`
  now refuse a filter, search text, `sort_by` or `group_by` on a hidden field
  and leave out its sums; `list_my_open_work_packages` is refused while
  `assignee` or `status` is hidden.
- Versions, sprints (17.3 and later) and backlog buckets (17.6 and later) shared
  into a covered project from a project outside `OPENPROJECT_READ_PROJECTS` are
  no longer named in work package results, `execute_query` rows, write results
  and previews, or version custom fields. A group named after one keeps its
  count and sums as `[outside read scope]`, and a version custom field accepts,
  by name or id, only versions a result may name. `version` names a version only
  when it is the whole assignment, and a sprint the token cannot view loses its
  name too. A restricted scope costs one cached lookup (five minutes) per
  version, sprint or bucket; under `*` nothing changes.
- A version, sprint or bucket whose defining project the token cannot see is
  covered under `*` and not under a restricted scope, on 16.x (link omitted) and
  17.x (placeholder) alike.
- A project link counts for `OPENPROJECT_READ_PROJECTS` and
  `OPENPROJECT_WRITE_PROJECTS` only if it points to a project on the configured
  instance; a link to another host or resource is denied, also under `*`.
- `create_grid` accepts only the scopes `/my/page`, `/projects/<identifier>` and
  `/projects/<identifier>/boards`, also under `*`.
- A project renamed in OpenProject 17.3 or later was still readable and writable
  through its former identifier when only that identifier matched
  `OPENPROJECT_READ_PROJECTS` or `OPENPROJECT_WRITE_PROJECTS`. A project now
  matches only by id, current identifier and name.
- Content of a project renamed while the server ran stayed admitted by its
  former identifier until the next rescan. The server now reads the current
  identifier first, one request per project and response.
- `list_work_packages` without a `project` counted work packages of a project
  renamed out of the read allowlist, by identifier or by name, in `total`,
  `groups` and `total_sums` for up to five minutes; it now reads the projects in
  its filter that no pattern matches by id and drops any that no longer match.
- `mark_notifications_read` ignored `OPENPROJECT_READ_PROJECTS`. It now marks
  only unread notifications about covered projects (refused when none is
  readable), and a notification outside the allowlist is refused, in the preview
  too.
- `update_relation` and `delete_relation` checked only the relation's source
  work package. Both work packages must now be covered by both allowlists,
  checked before the preview.
- `list_work_package_meeting_agenda_items` leaves out items of meetings in
  projects the read allowlist does not cover and counts only what it returns.
- `list_versions` with a `project` and version lookups by name inside a project
  leave out versions defined outside the read allowlist, and the allowed values
  in `get_project_work_package_context` and `get_project_admin_context` leave
  out such versions, sprints and buckets; a shared version defined outside the
  allowlist can no longer be assigned by name.
- `list_time_entry_activities` names only projects the read allowlist covers.
- Write previews, the `copy_project` preview and `get_board` show a title only
  for links to resources everyone sees alike (type, status, priority, users,
  roles, target project) and the link for any other.
- `get_project`, `list_projects` and the project results of writes no longer
  name a parent or ancestor project outside the read allowlist; work package
  reads, lists, `execute_query`, write results and the `delete_work_package`
  preview no longer show the id of a parent in such a project, and the delete
  preview no longer shows its children and ancestors.
- `list_work_packages` and `search_work_packages` no longer count, group or sum
  work packages of subprojects outside the read allowlist; under a restricted
  scope the filter names the covered subprojects itself and turns the expansion
  off; under `*` nothing changes.
- `get_work_package_activities` leaves out change details unless the read scope
  is `*` and whenever a hidden field could appear in them; the entry and the
  `add_work_package_comment` result carry `details_omitted: true`.
- `render_text` is refused unless `OPENPROJECT_READ_PROJECTS` is `*` and no
  field of work packages, projects, versions, documents, meetings, posts, users,
  groups, principals or views is hidden, because macros such as `#123` rendered
  names regardless of scope.

### Added

- Listed in the official MCP Registry as
  `io.github.jtauschl/openproject-ce-mcp`.
- Installable on macOS with Homebrew: `brew tap jtauschl/tap`, `brew trust
  --formula jtauschl/tap/openproject-ce-mcp`, `brew install openproject-ce-mcp`.
- Every tool declares MCP tool annotations (read-only, destructive, idempotent,
  open-world), so clients can tell reading tools from tools that change or
  delete data.

### Changed

- `list_work_package_wiki_links` says it checks only the work package against
  `OPENPROJECT_READ_PROJECTS`, because a link carries no project.
- Tool descriptions state each action and its consequences, delete tools say
  when a deletion cannot be undone, shared parameters describe themselves in the
  schema, and `select` lists every field it accepts.
- If `OPENPROJECT_BASE_URL` has a different path than OpenProject uses in its
  links (for example behind a path-rewriting proxy), project checks fail with a
  `[configuration_error]` naming both paths; they used to pass unchecked under
  `*`. Set `OPENPROJECT_BASE_URL` to the path OpenProject itself uses.
- A capability without a project (the global context) is visible only when
  `OPENPROJECT_READ_PROJECTS` is `*`.
- The server instructions name every opt-in tool group, so an agent can tell a
  missing tool is switched off.
- `configure` and `doctor` read Codex's configuration from `CODEX_HOME` when it
  is set.
- With Codex installed, `doctor` runs `codex mcp list` up to twice (at most 20
  seconds each); Codex may contact configured HTTP MCP servers.
- The package declares `pydantic` 2.12 or newer and `typing-extensions` 4.16 or
  newer, installs `httpx` (below 0.29) with its SOCKS extra so a `socks5://`
  `ALL_PROXY` starts, and on Python 3.10 depends on `tomli`.
- An allowlist pattern like `my-project` also matches a project named "My
  Project" in `list_projects`, `get_project`, `update_project` and
  `create_project`, as it already did elsewhere.

### Fixed

- `doctor` finds a project's Claude Code local-scope entry on Windows whether
  `~/.claude.json` keys it with backslashes or with the forward slashes `git`
  prints.
- On OpenProject 17.8 and later, where a work package can have several versions
  (the default of the 17.8 and 17.9 images), `create_work_package`,
  `create_subtask`, `update_work_package` and the bulk tools reported success
  for `version` but assigned nothing, and `version: none` cleared nothing. They
  now write it through `target_versions` there, so the result shows the
  assignment.
- A missing resource in a version-gated feature (meetings and their parts, wiki
  page links, user working hours and non-working times, reminders, project
  favorites) was reported as "requires OpenProject X or newer; this instance
  appears to be older", also on a current instance. The error now says the
  resource was not found, or that the feature is not available and needs that
  release.
- A collection was treated as read to its end when a page came back shorter than
  asked, so on an instance with a lower maximum page size later elements went
  missing (versions, sprint names, relations, time entry sums, reminders,
  notifications, project searches, saved queries, scanned results under a
  restricted scope). A collection now ends at the server's `total` or an empty
  page, and at startup the server lowers `OPENPROJECT_MAX_PAGE_SIZE` and the
  default page size to the instance maximum, with a warning.
- A form field with several violated constraints showed only "Multiple field
  constraints have been violated."; the nested messages are now listed.
- A board filter operator without a title came back percent-encoded (`%3D`); it
  is `=` now.
- With identifier-based allowlists every response re-read each linked project.
  The projects of a response are now read in one request, once per tool call.
- The current user, statuses, priorities and instance configuration were cached
  until restart; they expire after five minutes, and concurrent first reads
  share one request.
- `list_work_packages` and `search_work_packages` stopped paging when the
  allowlist dropped a row of a full page; `next_offset` now follows the server
  page.
- `list_work_package_attachments(include_total_size=true)` returned the sum of
  the first `OPENPROJECT_MAX_RESULTS` attachments as the total; it now returns
  none then.
- `update_board` with only `hidden` is refused like an empty update, and
  `create_board` and `update_board` no longer send or preview `hidden`, which
  OpenProject discards.
- `list_time_entries` with `user` compared display names, mixing up users who
  share one. The reference ("me", id or exact name) is resolved to an id among
  the users the token can see, a shared name is reported as ambiguous, and time
  entries carry `user_id` beside `user` (hidden together), which works for a
  user no longer visible by name.
- The `user` of an activity and of a comment posted with
  `add_work_package_comment` was always empty; it is read from the user (one
  request per distinct user, cached five minutes) unless hidden.
- `assignee: "me"` and a version, sprint or project given by name failed with a
  permission error when another tool group's read switch was off; those lookups
  no longer check it.
- `OPENPROJECT_TIMEOUT`, `OPENPROJECT_RETRY_BASE_DELAY` and
  `OPENPROJECT_RETRY_MAX_DELAY` accepted `nan` and `inf`, a non-finite
  `Retry-After` was used, and a huge time entry duration became infinity; all
  are rejected or ignored now.
- `update_work_package` and `bulk_update_work_packages` refuse to change
  `version`, `target_versions`, `sprint` or a version custom field while the
  work package holds such an assignment outside the read scope; the change would
  have removed it unseen.
- `execute_query` rows kept values of hidden custom fields, their comments, and
  the description length and truncation flag of a hidden `description`; they are
  masked like every other work package read.
- `render_text` failed with `OpenProject returned invalid JSON` on every
  supported version; it now returns the rendered markup as `html`.
- The SBOM named an `unknown` component and no dependency edges; it is exported
  from the lock file with `openproject-ce-mcp` as root and every runtime
  dependency.
- The items of `bulk_create_work_packages` and `bulk_update_work_packages` are
  checked against a schema the tool input schema lists. A wrong type used to be
  converted (`true` for a subject became "True") or crash the validator; it is
  refused with its position (`items.2.subject`) before any request, like an
  unknown key or a missing `project`, `type`, `subject` or `work_package_id`.
- The reminder tools answered a bare not-found on OpenProject 16.0; they now say
  they need 16.1 or newer.
- Help texts and the bodies of GitHub pull requests and GitLab issues and merge
  requests now carry the `<user-content>` delimiter.
- `responsible`, `priority`, `category`, `project_phase` and custom field
  options given by title wrote the first of several matches; they report the
  title as ambiguous and name the ids, like `assignee`, and so does a custom
  field name shared by two fields.
- A user or group given by name (an assignee, a responsible, a reference in the
  user and group tools) and `list_principals(search=...)` treated `_` and `%` as
  wildcards and read only the first page of matches; the text is searched
  literally and every page is read, so a second exact match is reported as
  ambiguous.
- `create_work_package`, `update_work_package`, `create_subtask` and the bulk
  update items accept a numeric `parent`, `assignee` and `responsible`; every
  other tool that takes a reference accepts the id as a JSON number. `get_user`,
  the user-schedule `user_ref` tools and the `list_time_entries` `user` filter
  pass the reference to OpenProject, which also matches the login.
- A project given as digits is looked up by id only and no longer falls back to
  a project whose name contains them; digits for category, priority, phase and
  `responsible` match by id only.
- `bulk_create_work_packages` rejects a boolean or decimal `project` or `type`.
- A confirmed `delete_project`, `delete_user` or `delete_group` no longer
  reports the deletion as done, because OpenProject only schedules it, and
  `delete_project` no longer returns the project as before.
- The `delete_user` and `delete_group` previews look the target up and show it,
  so a wrong id fails before approval.
- `list_work_package_file_links` takes `offset` and `limit`, so file links
  beyond the first page can be listed with the `next_offset` it returns.
- Tool descriptions and docs no longer state wrong facts: `get_project`,
  `set_project_favorite` and `list_sprints` accept a project name; agenda item
  tools need 17.6 and `list_work_package_meeting_agenda_items` 17.7;
  `update_recurring_meeting` changes materialized occurrences and can delete
  cancelled ones; a cancelled occurrence can be restored; `end_after` takes
  `specific_date`; the storage, user non-working time and watcher tools describe
  their checks and effects correctly; older-server errors are `[not_found]`;
  `OPENPROJECT_LOG_LEVEL` accepts `DEBUG`.
- `version_status` needs OpenProject 16.4; a rejected call keeps OpenProject's
  message and adds that an older instance does not support it.
- `OPENPROJECT_VERIFY_SSL=false` and the proxy settings (`HTTP_PROXY`,
  `HTTPS_PROXY`, `ALL_PROXY` including `socks5://`, `NO_PROXY`) take effect
  while retries are enabled, the default; before they worked only with
  `OPENPROJECT_MAX_RETRIES=0`.
- Project grids, including the boards page grid, are matched against the
  allowlists by their project; boards page grids were hidden from `list_grids`
  and `get_grid` and could not be updated or deleted.
- `list_time_entries`, `list_documents`, `list_news`, `list_views`,
  `list_boards` and `list_project_storages` with a `project` filter no longer
  return items of another project with the same name.
- `search_work_packages` no longer looks up each free-text term as a work
  package; only numeric ids and display ids like `PROJ-42` are, and any other id
  is rejected before a request.
- A work package id with leading zeros, such as `007`, resolves on OpenProject
  17.4 and later.
- Starting the server with missing or invalid configuration prints a short error
  naming the problem and exits with status 1 instead of a traceback.
- `doctor` lists the meeting and user-schedule write settings in its scope
  summary.
- `doctor` checks each MCP client's OpenProject entry on its own, with that
  client's way of passing variables and the entry's proxy and certificate
  settings; an incomplete or broken entry is no longer hidden by another
  client's entry or by the shell running `doctor`.
- `configure --help` and `openproject-ce-mcp-setup --help` show the command that
  was run.
- `create_board` and `update_board` apply a `sort_by` written as `"id:asc"` or
  as a bare field (ascending); OpenProject used to drop it silently.
- A board `sort_by` direction in upper or mixed case (`"id-DESC"`) sorts in that
  direction instead of ascending, and an invalid one (`"id-up"`) is rejected.
- `list_work_packages` and `search_work_packages` accept a `sort_by` written as
  `"status-desc"` as well as `"status:desc"`.
- `get_query_sort_by` accepts `"field:direction"`, `"field-direction"` or a bare
  field name; a bare name used to fail with not found.
- The wiki link tools name the release they need: `list_work_package_wiki_links`
  17.5, `delete_work_package_wiki_link` 17.6, `create_work_package_wiki_link`
  17.7 (17.6 was reported as too old for it); on 17.5 an OpenProject bug usually
  makes the delete fail earlier with a server error.
- `delete_work_package_wiki_link` with the id of an inline link (from a wiki
  link in the work package's description or from a wiki page that mentions it)
  is rejected before the request, with the hint to edit that text; only relation
  links can be deleted, with the "Manage wiki page links" permission.
- The sprint tools say they need OpenProject 17.3 or later, and `get_sprint`,
  `get_backlog_bucket` and a sprint given by id name the version the sprint API
  (17.3) or the bucket API (17.6) needs.
- `update_recurring_meeting` without `title` (for example to change `iterations`
  or `start_time`) no longer erases the titles of materialized future
  occurrences on OpenProject 17.4 and later.
- `mark_notifications_read` without `notification_id` changes only unread
  notifications, so already-read ones keep their `updatedAt` and a repeated call
  changes nothing.
- An invalid `select` error says that no request was sent, and the bulk
  descriptions say that `select` names write-result fields.
- `create_user_working_hours` and `update_user_working_hours` sent
  `availability_factor` as a decimal OpenProject rejects; it is a whole number
  from 0 to 100 now, and anything else is rejected before a request.
- `update_work_package` read a boolean `percentage_done` as a number (`true` set
  1 percent) and accepted `40.0` or `"40"`; it takes only a whole number from 0
  to 100.
- `delete_meeting` deleted the template meeting of a recurring series when given
  its id; it is rejected before the preview, and `delete_recurring_meeting`
  deletes the series.
- `create_meeting` silently dropped `state` and `notify`, which OpenProject
  always starts as draft and off; they are rejected with a pointer to
  `update_meeting`.
- `create_meeting` dropped `participant_user_refs` (the meeting got only its
  creator); it now has exactly the named participants, and an empty list is
  rejected. `update_meeting` rejects `participant_user_refs`, which OpenProject
  17.4 and 17.5 would append as duplicates and cannot remove.
- `sort_by` and `group_by` on the work package lists rejected columns
  OpenProject offers (`observed_in_versions`, `target_versions`, `sprint`,
  `backlog_bucket`, `position`); a column that needs a newer release comes back
  with OpenProject's rejection plus that release (`project_phase` 16.1, `sprint`
  17.4, `backlog_bucket` 17.6, `target_versions` 17.8, `observed_in_versions`
  17.9).
- A project reference or `list_projects` search containing `_` or `%` matched
  other projects (`a_b` and `axb`); the text is searched literally.
- Tool arguments were converted instead of checked (`true` read as id 1,
  `confirm` accepted `"yes"` and `1`, so a delete ran on a non-`true` answer).
  Each argument must now arrive with its own JSON type; a mistyped one is
  rejected before any request with `[validation_error]` and the argument's name,
  a list sent as JSON text still works, and `NaN` and `Infinity` are no numbers.

Thanks to our contributor: [@webadmin-stattreisen](https://github.com/webadmin-stattreisen) ([#45](https://github.com/jtauschl/openproject-ce-mcp/pull/45)).

## [0.4.2] - 2026-10-09

### Security

- Bumped `pyjwt` and `urllib3` to fix known vulnerabilities in transitive
  dependencies.
- `list_work_packages` without a project counted work packages of projects that
  matched only `OPENPROJECT_WRITE_PROJECTS` in `total`, group counts and sums;
  the work packages themselves were already left out.

### Changed

- Source-audited and runtime-smoke-tested against OpenProject 17.9.

### Fixed

- The server no longer limits long-text writes (descriptions, comments, custom
  field strings) to 10,000 characters, so work packages whose description grew
  longer in the web editor can be edited again.
- The server instructions no longer list Budgets as Enterprise-only; they are in
  the Community Edition.
- `bulk_create_work_packages` and `bulk_update_work_packages` rejected the
  per-item fields `index`, `success` and `error` in `select`, and
  `get_work_packages` rejected `success` and `error`, although every item
  carries them regardless of `select`; naming them is accepted and leaves the
  item untouched.
- `list_time_entry_activities` failed on servers that answer the
  `time_entries/activities` probe with HTTP 400 instead of 404; the per-project
  fallback now runs then too.
- With `mcp` 2.1 or later, rejected input and failed OpenProject calls reached
  the agent only as `Error executing tool <name>`; the error category and
  message are shown again.
- With `mcp` 2.1 or later, a call with an unknown argument was logged as a
  server crash with a traceback; it is logged as a rejected call.
- Projects created after the server started (a copy, the web UI, another client)
  were denied by identifier- or pattern-based `OPENPROJECT_READ_PROJECTS` and
  `OPENPROJECT_WRITE_PROJECTS` entries until a restart, and `list_work_packages`
  without a project left out their work packages. They are recognized from the
  responses that link them, and the list includes them within five minutes.
- `list_work_packages` without a project failed with "Project filter has invalid
  values" when an archived project matched `OPENPROJECT_READ_PROJECTS`.
- The `CONTRIBUTING.md` links on the PyPI project page now point to the
  repository.

## [0.4.1] - 2026-09-22

### Security

- Meeting agenda items and meeting outcomes now enforce the write project
  allowlist on a linked work package, closing a gap where linking could
  bypass `OPENPROJECT_WRITE_PROJECTS`.
- Sanitized tool error messages no longer allow a caller-influenced value to
  suppress the intended error category.
- Bumped `anyio`, `click`, and `httpx2` to fix known CVEs in transitive
  dependencies (found via `pip-audit`; not reachable through this project's
  own code paths, upgraded as a precaution).

## [0.4.0] - 2026-09-12

Complete the layered `app/` architecture migration so the codebase can scale
beyond a monolithic client while expanding and hardening the Community Edition
tool surface. This release adds new domains, richer work-package and attachment
capabilities, simpler installation, clearer permission and error behavior, and
broader OpenProject version compatibility.

### Security

- Updated `cryptography` to 50.0.0 to fix the high-severity
  GHSA-g6cj-pr64-35w5 padding-oracle vulnerability.
- Hidden project fields no longer leak through the available-parent-projects
  list.
- Unexpected bulk work-package errors no longer expose internal details.

### Added

#### Attachments

- `get_attachment_content` returns bounded image or text content for supported
  attachments and a clear skip reason for unsupported or oversized files.
- `list_work_package_attachments` gains `include_images`, inlining the listed
  images under one aggregate byte budget and reporting per-attachment skip
  reasons in `images`.

#### Work packages

- `list_work_packages`/`search_work_packages` gain `include_sums` (server-
  computed group aggregates), `overdue_only`/`due_within_days` (due-date
  filtering), and `custom_field_filters` (filter by custom field value).
- `bulk_update_work_packages` now supports `sprint`.
- `bulk_create_work_packages`/`bulk_update_work_packages` item fields now
  accept `parent` as well as `parent_work_package_id`, and both gain a
  `select` parameter to shrink an unconfirmed preview's echoed payload.
- `get_project` now returns the project's ancestor chain (`ancestors`).
- `get_work_package_relations` results now carry `queried_perspective`, a
  caller-relative reading of the relation (direction, effective type).
- `list_work_packages`/`search_work_packages`/`get_work_package`/
  `get_work_packages`/`list_my_open_work_packages` now expose custom field
  values.
- Work-package results now expose `has_project_attributes` on OpenProject
  17.7 and later.
- `create_work_package`/`create_subtask`/`update_work_package` (and both
  bulk tools' per-item fields) gain `target_versions`, OpenProject 17.7+'s
  multi-value successor to `version` — cannot be combined with `version`
  in the same call. Every work package result now also carries
  `target_versions`; `version` stays as a derived single-value field,
  `None` when more than one target version is assigned.

#### Search and result shaping

- `list_documents`, `list_views`, and `list_sprints` gain a `search`
  parameter.
- `get_document`, `get_news`, `get_wiki_page`, and meeting agenda-item and
  outcome lists gain per-call text limits; documents and news return their
  full descriptions by default.
- `get_work_package`, `list_actions`, `list_capabilities`, `list_time_entries`,
  `list_notifications`, meeting lists, and attachment lists gain response-field
  selection; attachment lists also gain pagination.
- Attachment lists can include total file size, and time-entry lists can
  include total hours.

#### New domains

- Wiki-link CRUD is available on OpenProject 17.6 and later.
- `execute_query` runs saved OpenProject queries.
- Storage tools manage external storages and project-storage connections.
- The Meetings domain covers meetings, agenda items, sections, outcomes, and
  recurring meetings.
- Costs read tools include `get_cost_entry`,
  `list_work_package_cost_entries`, `get_work_package_costs_by_type`,
  and `get_cost_type`.
- GitHub/GitLab integration links, forum posts, and Backlogs buckets have
  dedicated read tools.
- Per-user schedule tools manage non-working times and working hours.

### Changed

#### Tool interface

- Tool descriptions are substantially shorter across the whole catalog,
  reducing the fixed per-session token cost of the tool catalog itself.
- A project-scoped read tool is no longer registered when
  `OPENPROJECT_READ_PROJECTS` is empty, matching how write tools already
  behaved.
- **Breaking:** project-favorite operations are consolidated into
  `set_project_favorite(favorite: bool)`.
- **Breaking:** user locking operations are consolidated into
  `set_user_locked(locked: bool)`.
- **Breaking:** work-package watcher operations are consolidated into
  `set_work_package_watcher(watching: bool)`.
- **Breaking:** notification-read operations are consolidated into
  `mark_notifications_read(notification_id=None)`.
- **Breaking:** `list_project_sprints` is replaced by
  `list_sprints(project=None, ...)`.
- **Breaking:** `maximum_attachment_file_size`/`file_size` output fields
  renamed to `maximum_attachment_file_size_bytes`/`file_size_bytes`.

### Removed

- **Breaking:** `get.ps1`/`get.sh` and `uninstall.ps1`/`uninstall.sh` are
  removed. Use `pipx`, or `git clone` with `uv sync --dev` for a source install.
- **Breaking:** removed client-constructed `url` fields (and a few sub-
  collection hrefs) from MCP output models across most domains — these
  never resolved to a real page.
- **Breaking:** every non-bulk write/delete result's `confirmed`/
  `requires_confirmation` boolean pair is replaced by a single `state`
  field. Bulk work-package writes are unaffected.
- **Breaking:** `search_work_packages`'s `query` parameter is renamed to
  `search`, matching every other search-capable tool.
- **Breaking:** `list_roles` now returns a paginated result instead of the
  complete role collection in one call.
- **Breaking:** the legacy env-var names deprecated in 0.3.0 are removed. Use
  `OPENPROJECT_READ_PROJECTS`/`OPENPROJECT_WRITE_PROJECTS`, the individual
  `OPENPROJECT_ENABLE_<GROUP>_READ` flags, `OPENPROJECT_ENABLE_EXTENDED_READ`,
  and `OPENPROJECT_ENABLE_PERSONAL_WRITE`; the old auto-confirm flags have no
  replacement.

### Fixed

- Some write rejections showed a generic message instead of the actual
  reason (e.g. a rejected storage connection on Community Edition). The
  specific reason is now surfaced.
- A permission-denied response could be misreported as an authentication
  failure if OpenProject's rejection bundled an unrelated detail message
  mentioning "token" or "authenticate".
- Time and cost entries now retain their work-package association on
  OpenProject versions earlier than 16.6.
- `list_projects` and `list_work_packages`/`search_work_packages` no
  longer report a false `truncated: true` when exactly the requested
  `limit` of allowed results exists and nothing else does.
- User-typed fields (`responsible`, and user/version reference custom fields)
  can now be set on work-package writes.
- Time-entry activities can now be resolved when OpenProject returns their
  allowed values as a link.
- `update_document`'s `description` field no longer corrupts the stored
  value into an unusable string.
- The setup wizard now offers the Meetings and per-user schedule (non-working
  times, working hours) tool groups — both were previously always on with no
  way to configure them through `configure`.

Thanks to our contributor: [@ThomasPIET](https://github.com/ThomasPIET) ([#32](https://github.com/jtauschl/openproject-ce-mcp/pull/32)).

## [0.3.8] - 2026-08-25

### Added

- `search_work_packages` resolves numeric and display IDs such as `PROJ-42`
  directly and returns the result separately as `exact_match`.

### Changed

- The setup wizard's quick-mode write-scope question now asks per category
  instead of offering only `none`/`work-packages`/`all`.

### Fixed

- Work-package writes can set `version` without a false conflict with target
  versions.
- The source installers install their dependencies before starting setup.
- The Windows installer keeps the calling PowerShell window open on failure
  and reports an unsupported Python installation clearly.
- Source installation works reliably with PowerShell 5.1 TLS defaults.
- The Windows setup wizard accepts pasted API tokens without corrupting them.

### Known Issues

- Source installation on Windows ARM64 (`win_arm64`) requires the Visual
  Studio Build Tools C++ workload because `cryptography` has no prebuilt wheel
  for this platform. Alternatively, use `win_amd64` or WSL. The missing wheel
  is tracked upstream in
  [modelcontextprotocol/python-sdk#3373](https://github.com/modelcontextprotocol/python-sdk/issues/3373).

## [0.3.7] - 2026-08-17

### Security

- Updated `cryptography` to 50.0.0 to fix the high-severity
  GHSA-79v4-65xg-pq6g padding-oracle vulnerability.

### Fixed

- `list_my_open_work_packages` now returns complete allowed results under a
  restricted project read scope, including matches beyond the first server
  page.
- User-typed fields (`responsible`, and user/version reference custom fields)
  can now be set on work-package writes: the candidates are read from the
  linked `allowedValues` collection when the schema embeds none.

Thanks to our contributor: [@mehow-vng](https://github.com/mehow-vng) ([#24](https://github.com/jtauschl/openproject-ce-mcp/pull/24)).

## [0.3.6] - 2026-08-10

### Changed

- **Breaking:** Client-constructed `url` fields and related collection links
  are removed from most output models. Server-provided `download_url`,
  `avatar_url`, `identity_url`, and resolvable `url` fields remain available.
- **Breaking:** `list_work_package_attachments`, `list_reminders`, and
  `list_work_package_file_links` now use `offset`/`limit` and return paginated
  results with `total`, `next_offset`, and `truncated`. Treat `total` as a
  lower bound and continue paging until `next_offset` is `null`.
- Batch work-package reads limit concurrent requests to ten.
- Project allowlist checks for relations, notifications, reminders, and work-
  package hierarchies run concurrently for faster restricted-scope reads.

### Fixed

- Tools reject unknown or misspelled arguments instead of silently using
  defaults.
- Generic setup instructions use a token-free example file instead of writing
  a real token to `.mcp.json`.
- Setup and uninstall operations report filesystem failures cleanly and
  continue processing other selected clients.
- Collection tools now honor requested page sizes, return reliable pagination
  state, and avoid hiding boards beyond the server's default result cap.

---

## [0.3.5] - 2026-08-02

### Added

- `create_time_entry_until` and `update_time_entry_until` accept start and end
  times and calculate the duration. Time-entry durations also accept
  fractional seconds.

### Changed

- **Breaking:** `create_time_entry` and `update_time_entry` no longer accept
  the unsupported `end_time` parameter. Use the new `*_until` tools when both
  start and end times are known.

### Fixed

- User locking, notification-read operations, and password-based user creation
  now succeed against the OpenProject API.
- Work-package field hiding remains effective when returning hierarchies under
  a restricted read scope.
- Name-based sprint lookup includes matches beyond the first page.
- Work-package and project context results no longer duplicate or expose
  non-writable schema fields.
- Truncated time-entry comments report their original length and truncation
  state.
- Malformed, invisible, or unrelated project and attachment links are denied
  consistently instead of passing scope checks.

---

## [0.3.4] - 2026-07-29

### Changed

- **Breaking:** The ineffective `lang` preference field is removed. Use
  `update_user`'s `language` field instead.

### Security

- Relation targets, job statuses, copied projects, categories, grids, and
  project memberships now consistently enforce project allowlists.
- API path IDs containing `.` or `..` segments are rejected before requests
  are sent.
- Hidden-field rules now cover time-entry `start_time`/`end_time` writes, user
  preference updates, and grid results.
- Project, document, version, attachment, reminder, relation, and activity
  descriptions, plus time-entry comments, are now consistently marked as
  untrusted user content.

### Fixed

#### Time entries and reminders

- Time-entry previews now reflect OpenProject validation, and named activities
  work for users with only the "Log own time" permission.
- Reminder updates and deletions no longer fail on every call.

#### Lists and lookups

- Relation, membership, attachment, time-entry, grid, notification, reminder,
  file-link, view, document, version, sprint, news, user, and group listings no
  longer hide results because of single-page or fixed-cap fetching.
- Pagination terminates safely when an endpoint ignores its requested page
  size.
- Capability, sort-by, and job-status lookups now return valid IDs and work on
  the supported OpenProject versions.
- Group results report the correct member count.

#### Work packages and projects

- Work-package reads work on classic OpenProject versions and tolerate hierarchy
  links without display IDs.
- Parent-project choices contain only allowed projects and no longer expose full
  project details.
- Bulk work-package updates accept `sprint`, and their validation errors name
  `assignee` and `responsible` consistently.
- File-link writes no longer report a fabricated work-package ID.

#### Preferences and metadata

- Extended metadata tools honor their read-enablement setting.
- Null link collections and user identity URLs are handled correctly.

---

## [0.3.3] - 2026-07-28

### Security

- Board moves, parent-project changes, work-package parent and relation changes,
  job statuses, capabilities, watchers, file links, hierarchies, attachments,
  reminders, groups, users, and grids now consistently enforce project scope and
  hidden-field rules.
- Project-scoped results no longer leak subjects, identifiers, names, or
  principals from disallowed projects.

### Fixed

- News, document, and time-entry truncation honor their own hidden-field
  settings.
- Emoji-reaction previews no longer require the work-package write feature to
  be enabled, while still enforcing the project write allowlist.
- Projects created, copied, or renamed become immediately available to scoped
  tools without a server restart.
- Unscoped work-package lists return a clear permission error when they cannot
  prove that all results are allowed.
- Capability filtering works on OpenProject 16.x.
- Grid lists are paginated.
- Permission-denied responses include OpenProject's specific error message.

---

## [0.3.2] - 2026-07-20

### Fixed

- Milestone work packages now return their actual start and due dates.
- Closing a work package without an estimated time now succeeds on the first
  attempt.

---

## [0.3.1] - 2026-07-18

### Fixed

- Bulk work-package writes report indexed errors for unknown item fields
  instead of silently dropping them.
- Bulk work-package creation preserves `estimated_time`, `remaining_time`, and
  `duration`.
- A write scope narrower than the read scope no longer rejects otherwise
  allowed writes.

---

## [0.3.0] - 2026-07-17

Harden project isolation with fail-closed scopes and mandatory confirmation for
every write. Expand work-package querying, scheduling, hierarchy, and Backlogs
support while making setup and responses easier to use.

### Added

#### Work packages

- `get_work_packages` reads up to 100 work packages in parallel with per-item
  errors, deduplication, and field selection.
- Work-package lists support sorting, grouping, and filters for assignee,
  status, priority, and created, updated, or due dates.
- Work-package reads and writes expose richer scheduling, time-tracking,
  metadata, hierarchy, and progress fields.
- Nullable assignee, responsible, category, project phase, version, and sprint
  links can be cleared with `none` in single and bulk updates.
- Backlogs-enabled instances gain sprint reads and writable work-package sprint
  links.

#### Reliability and setup

- Transient HTTP failures are retried with configurable exponential backoff.
- `list_versions` supports text search, and project references fall back to an
  exact display-name match.
- The new `doctor` command diagnoses configuration and connectivity end to end.

### Changed

- **Breaking:** Every write and delete now requires `confirm=true`;
  `OPENPROJECT_AUTO_CONFIRM_WRITE` and `OPENPROJECT_AUTO_CONFIRM_DELETE` no
  longer bypass confirmation.
- **Breaking:** Project scopes are renamed to `OPENPROJECT_READ_PROJECTS` and
  `OPENPROJECT_WRITE_PROJECTS` and now deny access when empty or unset. Update
  configurations that still use the former `OPENPROJECT_ALLOWED_PROJECTS*`
  names before upgrading.
- **Breaking:** Personal, administrative, and extended read tools now require
  their dedicated opt-in scopes, which default to disabled.
- **Breaking:** Project-scoped write feature flags now default to enabled, with
  the fail-closed `OPENPROJECT_WRITE_PROJECTS` scope remaining the effective
  gate. Administrative and personal write flags remain disabled by default.
- **Breaking:** Attachment uploads no longer use the current directory as a
  fallback. `OPENPROJECT_ATTACHMENT_ROOT` must be configured as an absolute
  path.
- Tool registration now requires every scope used by a tool to be enabled.
- Setup gains quick, advanced, and non-interactive modes, a live connection
  test, and a final configuration preview.
- Hidden fields are omitted instead of returned as null, responses are more
  compact, and single work-package reads return long text in full.

### Fixed

- `OPENPROJECT_LOG_LEVEL` is honored and accepts `DEBUG`.
- Project, version, sprint, user, and group listings paginate correctly under
  search and restricted project scopes.
- Work-package field selection includes requested metadata, and list results
  expose `parent_display_id`.
- User write previews now use OpenProject's form validation.
- Work-package comments report the correct author without leaking unrelated
  activity details.
- Text fields can be cleared with an empty string across supported update
  tools.
- Bulk item IDs, scalar values, and ambiguous type names are validated without
  crashes or unsafe coercion.

### Security

- User-provided content is delimited and identified as untrusted.
- Sprint lists, reference resolution, and deprecated scope handling no longer
  allow cross-project data exposure or writes.
- Watcher and activity fields honor their hidden-field settings.
- List totals no longer reveal matches in disallowed projects.

---

## [0.2.3] - 2026-07-07

### Fixed

- Work-package attachment uploads no longer fail with a server error.
- The MCP initialization handshake reports this package's version.

### Added

- The MCP initialization response explains Community Edition API limits to
  connected agents.
- Work packages can be nested, re-parented, or detached with the new `parent`
  parameter.

---

## [0.2.2] - 2026-07-06

### Security

- File-link deletion and activity emoji reactions now enforce the project write
  allowlist.

### Fixed

- Group reads no longer crash when members are visible.
- Time-entry creation accepts semantic work-package references.
- Validation errors for `responsible` name the correct field.
- `openproject-ce-mcp configure` now exits cleanly on Ctrl+C.

### Changed

- A remote plain-HTTP base URL now warns that the API token will be transmitted
  without encryption.

---

## [0.2.1] - 2026-07-01

### Changed

- Setup now asks independently about global and project-scoped registration and
  writes only the selected targets.
- Re-running setup preserves existing values field by field.
- The writable-project prompt clarifies that `*` means all readable projects.

### Added

- Setup gives client-specific restart instructions.
- `configure --uninstall` also removes project-local registrations in the
  current directory.

---

## [0.2.0] - 2026-07-01

Publish the first PyPI release under the `openproject-ce-mcp` name. Add a
guided setup command and a top-level command-line interface for installation
and client registration.

### Added

- PyPI distribution, installable with `pip`, `pipx`, or `uv tool install`.
- `openproject-ce-mcp configure` registers the server with detected MCP
  clients.
- Top-level CLI: `openproject-ce-mcp --help`/`--version`.

### Changed

- The package is renamed to `openproject-ce-mcp`; the MCP server key remains
  `openproject`, so existing client registrations keep working.

### Fixed

- The shell installer no longer crashes on its first interactive prompt.
- Re-running `configure --global` pre-fills from an existing client
  registration.
- `configure` warns before writing a token-bearing `.mcp.json` into an
  unrelated project directory.

---

## [0.1.0] - 2026-07-01

Deliver the first Community Edition MCP server with broad OpenProject API v3
coverage. Provide guarded read and write access, compact MCP responses, and an
interactive setup flow for supported clients.

### Added

#### Core OpenProject domains

- Read and write tools cover projects, work packages, versions, boards,
  memberships, users, groups, news, notifications, grids, preferences, and
  time entries.
- Read or API-supported update tools cover documents, wiki pages, categories,
  instance configuration, query metadata, help texts, working days, custom
  options, actions, capabilities, and text rendering.
- Work-package tools include structured and free-text search, subtasks,
  comments, relations, activity history, bulk writes, watchers, attachments,
  and Nextcloud file links.
- Project-prefixed work-package identifiers such as `PROJ-123` are accepted by
  single-item, relation, and parent operations; numeric IDs remain canonical.

#### Setup and safety

- Interactive setup detects Claude Code, Claude Desktop, Codex, Cursor, and VS
  Code/Copilot and can register or remove the server in their configurations.
- Read, write, and administrative capabilities have independent feature gates,
  with write access disabled by default.
- Project allowlists match identifiers, names, numeric IDs, and glob patterns
  case-insensitively.
- Writes and deletes use a preview-and-confirm flow, while OpenProject role
  permissions remain the final authority.
- Attachment uploads are confined to `OPENPROJECT_ATTACHMENT_ROOT` and reject
  paths outside it as well as credential and configuration files.
- Field-hiding settings apply to reads and writes, and list results remain
  bounded and compact.

### Security

- Project allowlists protect relations, reminders, copied projects, and other
  linked resources from cross-project access.
- Hidden work-package subjects are not exposed through relation tools.
