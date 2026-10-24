# Changelog

All notable changes to this project will be documented in this file. Versions
follow [semantic versioning](https://semver.org); 0.2.0 is the first release
published to PyPI, 0.1.0 is the first tagged release, and 0.0.1 is the
development baseline.

---

## [0.4.3] - Unreleased

### Security

- A work package of a covered project can carry a version shared into its
  project from a project that `OPENPROJECT_READ_PROJECTS` does not cover, and
  from OpenProject 17.3 a sprint, and from 17.6 a backlog bucket, shared the
  same way. Work package reads, lists, searches, `execute_query` rows, write
  results and the delete preview named it in `version`, `target_versions`,
  `sprint` and the values of version custom fields, and `groups` named it when
  grouped by such a column. They now leave the name out as if it were unset,
  a group named after one keeps its count and sums under the label
  `[outside read scope]`, and `version` names a version only when it is the
  whole assignment. Under a restricted scope the server reads the defining
  project of each version, sprint or bucket a result names once and remembers
  it for five minutes; under `*` nothing is looked up. A sprint the token has
  no right to view loses its name too, because its project cannot be read.
- A version, sprint or backlog bucket whose defining project the token cannot
  see is covered under `*` and not covered under a restricted scope on every
  supported release; OpenProject 16.x leaves the project link out and 17.x
  renders an undisclosed placeholder, and the two behaved differently.
- A project link now counts for `OPENPROJECT_READ_PROJECTS` and
  `OPENPROJECT_WRITE_PROJECTS` only when it points to a project on the
  configured OpenProject instance; wherever a project link is checked, a link
  to another host or to a different resource is denied, also under `*`.
- `create_grid` accepts only the scopes `/my/page`, `/projects/<identifier>`
  and `/projects/<identifier>/boards`, after the instance's root path on a
  subpath install, and rejects any other scope before a request, also under
  `*`.
- A project renamed in OpenProject 17.3 or later could still be read and
  written through its former identifier when only that identifier matched
  `OPENPROJECT_READ_PROJECTS` or `OPENPROJECT_WRITE_PROJECTS`. A project now
  matches only by its id, current identifier and name.
- Content of a project renamed in OpenProject while the server ran, such as
  listed work packages, versions or time entries, was still admitted when only
  the project's former identifier matched `OPENPROJECT_READ_PROJECTS` or
  `OPENPROJECT_WRITE_PROJECTS`, until the server next rescanned its projects.
  When only a linked project's identifier decides the check, the server now
  reads the project's current identifier first, one request per project and
  response.
- `list_work_packages` without a `project` could count the work packages of
  a project renamed out of `OPENPROJECT_READ_PROJECTS`, by identifier or by
  name, in `total`, `groups` and `total_sums` for up to five minutes. Before
  each such list the server now reads every project in its filter that no
  pattern matches by id, one request per page of projects, and leaves out any
  that no longer matches.
- `mark_notifications_read` ignored `OPENPROJECT_READ_PROJECTS`. Without
  `notification_id` it marked notifications about every project read; it now
  marks only unread notifications about projects the read allowlist covers,
  and refuses without sending a write request when no project is readable.
  With `notification_id`, a notification about a project outside the
  allowlist is now refused, in the preview too. Under `*` both behave as
  before.
- `update_relation` and `delete_relation` checked `OPENPROJECT_READ_PROJECTS`
  and `OPENPROJECT_WRITE_PROJECTS` only against a relation's source work
  package. A relation from a work package in the allowlists to one outside
  them could be changed, including its type (which could make the outside
  work package the relation's source), or deleted, and the preview and
  result showed the outside work package's id and subject. Both work
  packages must now be covered by both allowlists, checked before the
  preview. When both allowlists are `*`, both tools behave as before,
  apart from one more request; a relation without a target link is
  refused.
- `list_work_package_meeting_agenda_items` returned every agenda item that
  links the work package, also those of meetings in projects outside
  `OPENPROJECT_READ_PROJECTS`. It now leaves out items of meetings whose
  project the read allowlist does not cover, and counts only the items it
  returns. It reads the project from the meeting the response embeds, so it
  sends no extra request.
- `list_versions` with a `project`, and every version lookup by name inside a
  project, returned versions defined in projects outside
  `OPENPROJECT_READ_PROJECTS`: OpenProject lists the versions shared into a
  project (system-wide, by tree or by hierarchy) next to its own. They are
  now left out per version, as in the list without a project, and
  `get_project_work_package_context` and `get_project_admin_context` leave out
  versions, sprints and backlog buckets of such projects in the allowed values
  of their fields. A shared version defined outside the allowlist can therefore
  no longer be assigned by name.
- `list_time_entry_activities` named every project that enables an activity,
  also those outside `OPENPROJECT_READ_PROJECTS`. It now names only the
  projects the read allowlist covers.
- Write previews echoed the title and display id of every link in
  OpenProject's form, so the subject of a parent work package or the name of a
  version outside `OPENPROJECT_READ_PROJECTS` could appear in a preview that
  never touched it. A preview now shows a title only for links to resources
  every user sees alike (type, status, priority, users, roles, the target
  project) and the href for any other link. `get_board` likewise shows the
  title of a filter value only for filters on such resources (status, type,
  priority, assignee, author, responsible) and the link for all others. The
  preview of `copy_project` is reduced the same way.
- `get_project`, `list_projects` and the project results of writes named
  parents and ancestors outside `OPENPROJECT_READ_PROJECTS`, and
  `get_work_package`, the work package lists, `execute_query`, the results of
  writes and the preview of `delete_work_package` showed the id and display id
  of a parent in such a project, and the delete preview also its children and
  ancestors. They now leave out a parent, ancestor or child the read allowlist
  does not cover.
- `list_work_packages` and `search_work_packages` could count, group and sum
  work packages of subprojects outside `OPENPROJECT_READ_PROJECTS`, because
  OpenProject adds the subprojects of every project a filter names. Under a
  restricted scope the filter now names the covered subprojects itself and the
  request turns the expansion off. Under `*` nothing changes.
- `get_work_package_activities` returned the change details OpenProject renders
  for each journal entry, such as `Parent set to <subject>` or `Project changed
  from <name> to <name>`, and that text can name a parent, project or version
  outside `OPENPROJECT_READ_PROJECTS`, or carry the value of a field hidden
  with `OPENPROJECT_HIDE_WORK_PACKAGE_FIELDS` or `OPENPROJECT_HIDE_CUSTOM_FIELDS`.
  OpenProject sends it in the API user's language with no structure to check
  against the allowlist, so the change details are now left out for every
  read scope other than `*`, identifier lists included, and whenever such a
  field is hidden, and `details_omitted` is true on the entry. Comments, user
  and time are unchanged. `add_work_package_comment` never returned details; its
  result now carries `details_omitted: true` for that.
- `render_text` rendered macros such as `#123`, `version#4`, `project#5` or
  `view#6` into the display id (with the project identifier) of any work
  package or the name of any version, project or view, whatever its project and
  whether or not `OPENPROJECT_READ_PROJECTS` covered it, in markdown and in plain
  text. It is now refused unless `OPENPROJECT_READ_PROJECTS` is `*` and no
  field of work packages, projects, versions, documents, meetings, posts, users,
  groups, principals or views is hidden.

### Added

- Listed in the official MCP Registry as
  `io.github.jtauschl/openproject-ce-mcp`.
- Installable on macOS with Homebrew from the `jtauschl/tap` tap:
  `brew tap jtauschl/tap`, `brew trust --formula jtauschl/tap/openproject-ce-mcp`,
  then `brew install openproject-ce-mcp`.
- Every tool declares MCP tool annotations (read-only, destructive, idempotent,
  open-world), so clients can tell reading tools from tools that change or
  delete data.

### Changed

- `list_work_package_wiki_links` now says that it checks only the work package
  against `OPENPROJECT_READ_PROJECTS`, because a wiki page link carries no
  project.
- Tool descriptions state each action and its consequences directly, delete
  tools say when a deletion cannot be undone, and the parameters most tools
  share describe themselves in the tool schema; `select` lists every field it
  accepts.
- If `OPENPROJECT_BASE_URL` has a different path than the one OpenProject uses
  in its links, for example behind a path-rewriting proxy, project checks now
  fail with a `[configuration_error]` naming both paths. Such links used to
  pass unchecked under `*`; set `OPENPROJECT_BASE_URL` to the path OpenProject
  itself uses.
- A capability without a project (the global context) is now visible only
  when `OPENPROJECT_READ_PROJECTS` is `*`.
- The server instructions name every opt-in tool group, so an agent can tell
  that a missing personal, admin or user-schedule tool is switched off, not
  broken.
- `configure` and `doctor` read Codex's configuration from `CODEX_HOME` when
  it is set.
- When Codex is installed, `doctor` runs `codex mcp list` up to twice (at most 20
  seconds each) to see the configuration Codex applies; Codex may contact
  configured HTTP MCP servers during that call.
- On Python 3.10 the package depends on `tomli`, which reads Codex's
  configuration.
- The package declares `pydantic` (2.12 or newer) and `typing-extensions` (4.16
  or newer), which it imports directly, and installs `httpx` with its SOCKS
  extra, so a `socks5://` proxy in `ALL_PROXY` starts without a manual install.
  `httpx` is limited to versions below 0.29.
- An allowlist pattern like `my-project` now also matches a project named
  "My Project" in the project tools, such as `list_projects`, `get_project`,
  `update_project` and `create_project`, as it already did in the checks on
  work packages and other project content.

### Fixed

- `OPENPROJECT_TIMEOUT`, `OPENPROJECT_RETRY_BASE_DELAY` and
  `OPENPROJECT_RETRY_MAX_DELAY` accepted `nan` and `inf`, which passed the
  minimum check and reached the HTTP client; they are now rejected at start.
  A `Retry-After` header that is not a finite number is ignored, and a
  time entry duration too large for a float no longer becomes infinity.
- `update_work_package` and `bulk_update_work_packages` now refuse a change of
  `version`, `target_versions`, `sprint` or a version custom field while the
  work package holds such an assignment in a project outside
  `OPENPROJECT_READ_PROJECTS`. The change replaced the whole value and removed
  an assignment the result no longer shows. The error names how many
  assignments are in the way and no name.
- `execute_query` rows kept the values of custom fields hidden by
  `OPENPROJECT_HIDE_CUSTOM_FIELDS`, their comments, and the description length
  and truncation flag when `description` is a hidden field, which every other
  work package read removes. `execute_query` and the work package reads now
  apply the same masking.
- `render_text` failed with `OpenProject returned invalid JSON` on every
  supported version, because OpenProject answers the render endpoints with
  `text/html` and the server parsed the answer as JSON. It now returns the
  rendered markup as `html`.
- The SBOM built with the package named an `unknown` component without a
  version where the project itself belongs, and listed no dependency edges. It
  is exported from the lock file now, names `openproject-ce-mcp` and its version
  as the root component, lists every runtime dependency reachable from it, and
  the build fails if that does not hold.
- The items of `bulk_create_work_packages` and `bulk_update_work_packages` are
  checked against a schema now, which the tool input schema lists. A value of
  the wrong type used to be converted (`true` for a subject became the text
  "True") or crashed the validator (a number for a description ended in an
  internal error); it is refused with its position (`items.2.subject`) before
  any request, like an unknown key or a missing `project`, `type`, `subject` or
  `work_package_id`.
- `list_reminders`, `create_work_package_reminder`, `update_reminder` and
  `delete_reminder` answered a bare not-found on OpenProject 16.0, which has no
  collection of reminders and no route to create, change or delete one. They
  now say that the call requires OpenProject 16.1 or newer, and the
  descriptions of the three writes state it.
- Help texts and the bodies of GitHub pull requests and GitLab issues and merge
  requests reached the agent without the `<user-content>` delimiter that marks
  text written by users, unlike every other text field. They carry it now.
- `responsible`, `priority`, `category`, `project_phase` and the options of
  custom fields, given by title, wrote the first of several allowed values
  that share the title (display names of users are not unique, and a version
  shared into a project can repeat a name), while `assignee` reported such a
  title as ambiguous. They report it as ambiguous too and name the matching
  ids, and a custom field name shared by two custom fields is ambiguous in the
  same way. Passing the numeric id still works.
- A user or group given by name (an assignee, a responsible, a reference in
  the user and group tools) and `list_principals(search=...)` treated `_` and
  `%` in the text as wildcards, and a name was looked up on the first page of
  matches only, so a wildcard match could push the exact name off it and the
  lookup reported it as not found. The text is searched literally now, and
  every page of the matches is read, so a second exact match on a later page
  is reported as ambiguous.
- `create_work_package`, `update_work_package` and `create_subtask` accept a
  numeric `parent`, `assignee` and `responsible` (a JSON number such as `7`),
  not only a string; `bulk_update_work_packages` items accept a numeric
  `assignee` and `responsible` too, and every other tool that takes a
  reference to a project, type, status, priority, version, category, phase,
  sprint, activity, user, principal or role accepts the id as a JSON number
  too. `get_user`, the user-schedule `user_ref` tools and the
  `list_time_entries` `user` filter pass the reference to OpenProject, which
  also matches it against the login.
- A project given as an all-digit value is looked up by id only; a missing id
  no longer falls back to a project whose name contains those digits.
  Category, priority, phase and `responsible` values given as digits match by
  id only, not by a title made of those digits.
- In `bulk_create_work_packages` items, `project` and `type` reject a boolean
  or a decimal number instead of using it as a name such as "True".
- A confirmed `delete_project`, `delete_user` or `delete_group` no longer
  reports the deletion as done: OpenProject only schedules it and deletes in a
  background job, and the message now says so. A confirmed `delete_project`
  no longer returns the project as it was before the deletion.
- The `delete_user` and `delete_group` previews look the user or group up and
  show it, so a wrong id fails before anyone approves the deletion.
- `list_work_package_file_links` takes `offset` and `limit`, so file links
  beyond the first page can be listed with the `next_offset` it returns.
- Tool descriptions no longer state wrong facts: `get_project`,
  `set_project_favorite` and `list_sprints` accept a project name too; the
  get, create, update and delete tools for agenda items and sections need
  OpenProject 17.6, and `list_work_package_meeting_agenda_items` needs 17.7,
  not 17.4; `update_recurring_meeting` changes already materialized future
  occurrences and can delete cancelled ones; a cancelled recurring meeting
  occurrence can be restored. `create_storage`, `delete_storage`,
  `update_user_non_working_time` and `set_work_package_watcher` describe their
  checks and effects correctly.
- The `list_work_packages` description and the installation guide now say
  that `version_status` needs OpenProject 16.4 or later. When OpenProject
  rejects a `list_work_packages` call that uses `version_status`, the error
  keeps OpenProject's own message, for example "Version Operator is not set to
  one of the allowed values", and adds that an instance older than 16.4 does
  not support `version_status`.
- `OPENPROJECT_VERIFY_SSL=false` and the proxy settings now take effect while
  retries are enabled, which is the default. They used to apply only with
  `OPENPROJECT_MAX_RETRIES=0`. Proxies come from `HTTP_PROXY`, `HTTPS_PROXY`
  or `ALL_PROXY`, `socks5://` URLs included, and a host listed in `NO_PROXY`
  is reached directly. Only while none of these variables is set do the
  system proxy settings apply on macOS and Windows, without the system's own
  proxy exceptions.
- Project grids, including the boards page grid of a project, are now matched
  against a restrictive `OPENPROJECT_READ_PROJECTS` and
  `OPENPROJECT_WRITE_PROJECTS` by their project. Boards page grids were
  hidden from `list_grids` and `get_grid` and could not be updated or deleted.
- `list_time_entries`, `list_documents`, `list_news`, `list_views`,
  `list_boards` and `list_project_storages` with a `project` filter no longer
  return items of another project with the same name.
- `search_work_packages` no longer requests each free-text search term as a
  work package; only numeric ids and display ids like `PROJ-42` are looked up
  directly. A work package id that is neither is rejected as invalid input
  before any request.
- A numeric work package id with leading zeros, such as `007`, now resolves
  on OpenProject 17.4 and later.
- Starting `openproject-ce-mcp` with missing or invalid configuration, such
  as no `OPENPROJECT_BASE_URL`, prints a short error naming the problem and
  how to set it up, and exits with status 1 instead of a Python traceback.
- `openproject-ce-mcp doctor` lists the meeting and user-schedule write
  settings in its scope summary.
- `openproject-ce-mcp configure --help` and `openproject-ce-mcp-setup --help`
  show the command that was run.
- `openproject-ce-mcp doctor` checks each MCP client's OpenProject entry on
  its own, with that client's way of passing environment variables; an
  incomplete or broken entry is no longer hidden by another client's entry or
  by the shell running doctor, and the connection check uses the entry's own
  proxy and certificate settings.
- `create_board` and `update_board` apply a `sort_by` criterion written as
  `"field:direction"`, for example `"id:asc"`, or as a bare field name, which
  sorts ascending. OpenProject used to drop such criteria without an error.
- A board `sort_by` direction written in upper or mixed case, such as
  `"id-DESC"`, now sorts in that direction instead of ascending, and an
  invalid direction such as `"id-up"` is rejected instead of sorting
  ascending.
- `list_work_packages` and `search_work_packages` accept a `sort_by` criterion
  written as `"field-direction"`, for example `"status-desc"`, as well as
  `"field:direction"`.
- `get_query_sort_by` accepts the id as `"field:direction"`,
  `"field-direction"` or a bare field name; a bare field name used to fail
  with not found.
- `create_work_package_wiki_link` needs OpenProject 17.7; on 17.6 it now says
  so instead of claiming the server is older than 17.6.
  `list_work_package_wiki_links` works from 17.5 and
  `delete_work_package_wiki_link` from 17.6, and on an older server each of
  these tools names the version it needs; on 17.5 an OpenProject bug usually
  makes `delete_work_package_wiki_link` fail earlier with a server error.
  Their descriptions and the tool reference state these versions and
  describe when OpenProject fails to list a work package's links, instead of
  naming versions where the tools do not exist.
- The `list_sprints` and `get_sprint` descriptions and the tool reference now
  say that sprints need OpenProject 17.3 or later. When `get_sprint`,
  `get_backlog_bucket` or a sprint given by id to `update_work_package` or
  `bulk_update_work_packages` is not found, the error now names the version
  the sprint API (17.3) or the backlog bucket API (17.6) needs.
- `update_recurring_meeting` without `title` no longer erases the titles of
  already materialized future occurrences. On OpenProject 17.4 and later such
  an update, for example of `iterations` or `start_time`, left those
  occurrences without a title, while the API could keep showing the old one
  for a while. The update now sends the series' current title along.
- `mark_notifications_read` without `notification_id` changes only unread
  notifications, as OpenProject's own "mark all as read" does. It used to
  write every notification again, so already-read notifications got a new
  `updatedAt` on each call; they now keep it, and a repeated call changes
  nothing.
- `delete_work_package_wiki_link` with the id of an inline link, which comes
  from a wiki link in the work package's description or from a wiki page that
  mentions the work package, no longer claims that the server is older than
  OpenProject 17.6. OpenProject cannot delete inline links through its API,
  so the tool now rejects one without sending the delete request and says to
  edit that text instead. The tool description and the tool reference say
  that only relation links can be deleted and that deleting needs the "Manage
  wiki page links" permission.
- An invalid `select` error now says that no request was sent, so a rejected
  confirmed bulk write is known to have written nothing. The
  `bulk_create_work_packages` and `bulk_update_work_packages` descriptions say
  that `select` names write-result fields and that `display_id` and the other
  work package fields come with `result`.
- `create_user_working_hours` and `update_user_working_hours` sent
  `availability_factor` as a decimal number, which OpenProject rejects as
  "not an integer", so no value could be set. It is now a whole number from 0
  to 100 (the percentage of working time dedicated to project work); a
  fraction, a boolean, a numeric string or a value outside that range is
  rejected before any request.
- `update_work_package` read a boolean `percentage_done` as a number, so `true`
  set the progress to 1 percent without a warning, and a fraction such as
  `40.0` or a numeric string such as `"40"` was accepted. It now takes only a
  whole number from 0 to 100; anything else is rejected before any request,
  as `bulk_update_work_packages` already did for its items.
- Tool descriptions and documentation stated facts that do not hold:
  `create_recurring_meeting` listed `end_after` as "date" (the value is
  "specific_date"), named only some frequencies (monthly ones need OpenProject
  17.5) and left out the monthly parameters;
  `init_recurring_meeting_occurrence` did not say that OpenProject 17.4 and
  17.5 fail with a server error for an occurrence that already exists. The
  user-schedule tools said an older server answers with a server error (it is
  `[not_found]` naming the 17.3 floor), `delete_work_package_wiki_link` said a
  missing permission gives `[permission_denied]` (OpenProject answers 404, so
  it is `[not_found]`), and `docs/tools.md` called the bulk work package tools
  numeric-only, listed `list_notifications` as unread-only, and claimed
  `get_my_preferences` returns the language. `OPENPROJECT_LOG_LEVEL` also
  accepts `DEBUG`.
- `delete_meeting` deleted the template meeting of a recurring series when
  given its id, leaving a series that could no longer create occurrences. It
  now rejects that id before the preview, as OpenProject's web interface does;
  `delete_recurring_meeting` deletes the whole series.
- `create_meeting` accepted `state` and `notify`, but OpenProject always
  starts a new meeting as a draft with notifications off, so both were
  silently dropped. They are now rejected with a message that points to
  `update_meeting`.
- `create_meeting` dropped `participant_user_refs`: OpenProject's create form
  leaves the list out of the request that is committed, so the meeting got
  only its creator. The participants are now part of that request and the
  meeting has exactly the named participants, the creating user only if
  named; an empty list is rejected. `update_meeting` could never change
  participants either: OpenProject 17.4 and 17.5 would add a user a second
  time and cannot remove anyone, and only administrators can read the server
  version that tells those releases from 17.6 and later. It now rejects
  `participant_user_refs` instead of ignoring it.
- `sort_by` on the work package list tools rejected `observed_in_versions`,
  `target_versions`, `sprint`, `backlog_bucket` and `position`, and `group_by`
  rejected the first four, although OpenProject offers them. A column that
  needs a newer OpenProject release than the instance runs now comes back with
  OpenProject's own rejection plus the release it needs (`project_phase` 16.1,
  `sprint` 17.4, `backlog_bucket` 17.6, `target_versions` 17.8,
  `observed_in_versions` 17.9). The parameter descriptions list every field and
  these releases.
- A project reference or a `list_projects` search that contained `_` or `%`
  also matched other projects, because OpenProject uses the search text as a
  LIKE pattern: a project named `a_b` could be confused with `axb`, and the name
  fallback for a project reference could pick the wrong project. The text is
  now searched literally.
- Tool arguments were converted instead of checked: `true` for an id was read
  as id 1, `"5"` and `5.0` passed for a count, and `confirm` accepted `"yes"`,
  `"true"` and `1`, so a delete ran on an answer that is not `true`. Every
  argument now has to arrive with its own JSON type (a number, a boolean, a
  string) and a mistyped one is rejected before any request, with the
  `[validation_error]` category and the argument's name but not its value. A
  list sent as JSON text still works. Text that looks like JSON (`null`,
  `[1, 2]`) stays text in a string argument instead of being decoded, and for
  a list argument the text `null` is rejected instead of read as missing.
  Lists of numbers are checked element by element, and `NaN` and `Infinity`
  are no numbers anywhere in an argument.

Thanks to our contributors: [@webadmin-stattreisen](https://github.com/webadmin-stattreisen) ([#45](https://github.com/jtauschl/openproject-ce-mcp/pull/45)).

## [0.4.2] - 2026-10-09

### Security

- Bumped `pyjwt` and `urllib3` to fix known vulnerabilities in transitive
  dependencies.
- `list_work_packages` without a project counted the work packages of
  projects that matched only `OPENPROJECT_WRITE_PROJECTS` in its total, group
  counts and sums; the work packages themselves were already left out.

### Changed

- Source-audited and runtime-smoke-tested against OpenProject 17.9.

### Fixed

- The MCP server no longer imposes a 10,000-character limit on long-text
  writes (descriptions, comments, custom field strings), so work packages
  whose description grew longer in the web editor can be edited again.
- The server instructions no longer list Budgets among the Enterprise-only
  features; Budgets are part of the Community Edition.
- `bulk_create_work_packages` and `bulk_update_work_packages` rejected the
  per-item fields `index`, `success` and `error` in `select`, and
  `get_work_packages` rejected `success` and `error`, although every item
  carries them regardless of `select`; naming them is now accepted and leaves
  the item untouched.
- `list_time_entry_activities` failed outright on servers that answer the
  `time_entries/activities` probe with HTTP 400 instead of 404; the
  per-project fallback now runs in that case too.
- With `mcp` 2.1 or later installed, rejected input and failed OpenProject
  calls reached the agent only as `Error executing tool <name>`; the error
  category and message are shown again.
- With `mcp` 2.1 or later installed, a call with an unknown argument was
  logged as a server crash with a traceback; it is now logged as a rejected
  call.
- Projects created after the server started (a copy, the web UI, another
  client) were denied by identifier- or pattern-based
  `OPENPROJECT_READ_PROJECTS`/`OPENPROJECT_WRITE_PROJECTS` entries until the
  server restarted, and `list_work_packages` without a project left out their
  work packages. They are now recognized from the responses that link them;
  `list_work_packages` without a project includes them within five minutes.
- `list_work_packages` without a project failed with "Project filter has
  invalid values" when an archived project matched
  `OPENPROJECT_READ_PROJECTS`.
- The links to `CONTRIBUTING.md` on the PyPI project page led nowhere; they
  now point to the repository.

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
  replacement. `OPENPROJECT_ALLOWED_PROJECTS`/`_READ`/`_WRITE` still emit a
  one-time startup/`doctor` warning naming their replacement and are prefilled
  by `configure`, unlike every other legacy name in this list — see
  [Configuration](docs/configuration.md#legacy-configuration-migration).

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

Thanks to our contributors: [@ThomasPIET](https://github.com/ThomasPIET) ([#32](https://github.com/jtauschl/openproject-ce-mcp/pull/32)).

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
