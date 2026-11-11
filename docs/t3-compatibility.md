# T3 compatibility and verification

Linux is the only supported development platform: `rtx6000` and `amd-halo-1`
through `amd-halo-5`. T3 is an optional worktree adapter. This repository owns action definitions in
`policy/t3-actions.json`. Generation merges those entries into `t3.json`.
Setup calls `./scripts/setup`, runs on creation and waits (`async: false`).
Check, test and review call their matching wrappers and are manual. None of the
four runs or stops on settle. The wrappers must pass locally before importing
or changing saved actions. No saved settings are changed by generation.

## Installed version and evidence

On 2026-11-10, `t3 --version` and the supported `t3_environment_read` tool both
reported 0.1.8 on RTX6000. The installed executable is
`~/.t3/runtime/versions/0.1.8/t3`, SHA-256
`9bb28f51f118ebc881b04859848e8895458e7f26c13d44e07d316442f8422074`.
Its bundled source was inspected read-only with `strings`; the client modules
are under the same version's `client/assets/`. Source paths below are the
paths recorded in that bundle, not an assumed upstream tag. This supersedes
the previous 0.0.45 compatibility notes. Other hosts were not inspected;
0.1.8 on all hosts is the owner's reported rollout baseline, not a measurement
from this task.

## Effective settings precedence

Verified in bundled `packages/shared/src/projectScripts.ts`, function
`resolveProjectScripts`, in order:

1. `projectSettingsOverrides[project.id].defaultProjectScripts`, if defined,
   wins, including an empty array.
2. When `projectSettingsFolded` is true, use environment `defaultProjectScripts`.
3. Otherwise, a legacy `projectScriptOverrides[project.id]` value of null means
   environment defaults. An array, including an empty one, overrides actions.
4. With no legacy override, nonempty saved `project.scripts` wins; otherwise
   use environment `defaultProjectScripts`.

These lists replace one another; they are not combined. Repository `t3.json`
actions are not an additional fallback in this resolver. Import is explicit.
Verified in installed `projectScripts-J0Gosp2K.js`: the import UI reads the file,
filters existing names or commands, then creates saved entries. Later file
updates do not synchronize saved actions. Editing only `project.scripts` may
have no effect when a higher-priority override exists.

For file-backed settings, bundled `packages/shared/src/projectSettings.ts`,
`resolveProjectSettings`, applies project overrides over environment settings.
Only a null resolved setting falls through to the file and then its built-in
default. `packages/contracts/src/t3ProjectFile.ts` lists file-backed settings:
`defaultThreadEnvMode` (built-in local) and `worktreeSubmodules` (recursive).
Actions are importable, not file-backed effective settings. An explicit
worktree environment preference can therefore shadow the repository mode.

## Lifecycle flags, settle actions and shortcuts

Verified in bundled `projectScripts.ts`: only the first action marked
`runOnWorktreeCreate` is selected, and only the first with `runOnSettle: true`
is selected for settlement. Order matters. The contract says settle actions run
in the thread worktree each time it settles, skipping threads without one.
`stopOnSettle` stops an action's terminal and children on settlement. Preserve
useful settle and stop behavior in separate actions; the canonical four are
not cleanup actions. Inventory all flags, including actions that are currently
shadowed, before rollout.

Verified in bundled `src/project/ProjectSetupScriptRunner.ts`: setup uses
`input.worktreePath` as cwd, with `T3CODE_PROJECT_ROOT` and
`T3CODE_WORKTREE_PATH` supplied. Missing `async` means asynchronous; explicit
false requests waiting. The tracked bootstrap path awaits observed synchronous
completion before releasing the prepared run, and raises an error on nonzero
exit. This is stronger than the historical 0.0.45 best-effort path. Waiting
requires completion observation and a supported shell. No universal failure
or resume guarantee follows from this source inspection.

Verified in installed `projectScripts-J0Gosp2K.js` and
`keybindings-ek_14oVk.js`: shortcuts are separate settings, associated with the
saved script ID, and the editor uses the last matching binding. They are not
fields in the repository action schema. Inventory effective bindings in the
selected environment's Settings > Keybindings and each action editor. Retain
local IDs when editing actions so shortcuts continue to target them. Do not
copy project IDs or saved action IDs between hosts.

## Read-only host inventory

Supported `t3_environment_read`, `t3_project_list` and `t3_project_read` expose
environment preferences and saved project scripts. They do not expose all
project settings overrides or keybindings. `t3 project --help` in 0.1.8 offers
add, remove and rename, with no settings-read CLI. Use the supported settings
UI for full effective settings. Do not edit databases, replace settings files,
or assume a saved project response alone proves effective actions.

This task also read only the action-related fields from
`~/.t3/userdata/settings.json` and script bindings from `keybindings.json`,
without printing unrelated fields or secrets. On RTX6000, repo-standard has:

- Environment default mode worktree; no serialized default actions (the
  bundled schema supplies an empty array).
- `projectSettingsFolded: true` and a project `defaultProjectScripts: []`
  override. The legacy script override is also an empty array.
- Before the live update, supported project reads returned `scripts: []` and no project mode override.
- No script keybindings in the keybindings file. No effective creation or
  settle action exists, because the winning action list is empty.

Live RTX6000 evidence on 2026-11-10: the supported `t3_project_update` tool
saved all four canonical actions to `project.scripts`. With
`projectSettingsFolded: true`, the server's `ProjectSetupScriptRunner` uses the
bundled `resolveProjectScripts`, which returns the empty project
`defaultProjectScripts` override without consulting `project.scripts`. A new
worktree thread (`chore/t3-pilot-setup`) ran no setup. Effective saved actions
require Settings UI replacement of the project action override; no supported
tool or CLI exposes that override. Live failure/resume tests were not run by
owner decision. Other hosts were not tested.

## Generation, audit and rollout

`repository.py adopt`, `update` and `audit` include planned `t3.json` changes.
Unrelated actions and top-level fields survive. Exact canonical duplicates
are collapsed. A canonical name with a different command, competing creation
action, extra local action fields, or canonical action with settle behavior
reports a manual integration conflict with an exact proposed diff. Apply refuses
to overwrite it. Fold repository setup behavior into the configured
finite setup steps beneath `./scripts/setup`, or preserve it as an unrelated
manual action, then rerun. The generator never drops that behavior silently.

The scheduled policy audit prints repository action and lifecycle inventory
before integrity validation. Aligned means the repository definition matches;
pending means missing or different actions or competing creation flags;
inaccessible means unreadable or malformed input. Host settings inventory is
unsupported in the unattended CLI audit and explicitly pending manual review.
The supported tools and settings UI allow a separate host inventory;
repository alignment is never reported as effective host alignment. Drift
still fails integrity validation; a canonical upgrade remains informational.

Use the supported Settings UI to replace the effective project action override,
retaining unrelated actions and local IDs. Importing a shadowed saved list does
not activate it. No further pilots or lifecycle testing are required by the
owner for this rollout.
