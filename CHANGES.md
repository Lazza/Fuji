# Fuji — FileVault read-only unlock

Changes to the Fuji (Lazza/Fuji) codebase to support unlocking a
FileVault-encrypted APFS Data volume from within macOS Recovery and
mounting it **read-only** for forensic acquisition.

Applies to Fuji 1.2.0 (commit layout as of April 2026). The following
files are touched across two sets of changes (initial feature, then
bug fixes):

**Initial feature additions:**

1. **New:** `shared/filevault.py` — GUI-free unlock helpers.
2. **New:** `checks/readonly.py` — read-only verification check.
3. **Modified:** `fuji.py` — `DevicesWindow` gains FileVault state,
   an unlock button, and a password dialog.

**Bug fixes and build hardening (April 2026):**

4. **Modified:** `fuji.py` — selection, double-click, and dialog fixes
   (see *Bug fixes* section below).
5. **Modified:** `Fuji.spec` — execute-bit fix for the launcher script.
6. **Modified:** `shared/environment.py` — execute-bit fix for the
   RAM-disk launcher after `ditto` copy.

No acquisition method, check, or environment logic is altered in ways
that affect evidence handling. No command is introduced that writes to
the source disk. (Note: `shared/environment.py` is modified, but only
in `attempt_ramdisk()` which operates exclusively on the tool's own
volatile RAM disk, not on any evidence volume.)

## Forensic contract

The implementation honours the stated constraints:

- **Read-only mount is mandatory.** The unlock flow is two steps:
  `diskutil apfs unlockVolume <id> -nomount -stdinpassphrase`, followed
  by `diskutil mount readOnly <id>`. The `-nomount` flag suppresses
  `diskutil`'s default auto-mount, which would otherwise come up
  read-write and violate the contract.
- **No writes to the source disk.** Nothing in the new code invokes
  `diskutil repairVolume`, `fsck_apfs`, journal replay, or any other
  mutating command. After mounting, `verify_readonly()` checks the
  kernel-level mount flags (parsed from `mount(8)`) to confirm the
  volume is genuinely read-only; if somehow it is not, `UnlockError`
  is raised rather than silently succeeding.
- **Password hygiene.** The password is passed to `diskutil` via
  stdin (`-stdinpassphrase`) so it never appears in argv (which is
  visible to other processes via `ps`). It is never written to a
  temp file, never logged, and never printed. The `subprocess.run`
  call uses `capture_output=True`; diskutil's stderr is classified
  into a generic error message rather than surfaced raw, so there
  is no risk of leaking a passphrase that might appear in an edge
  case. References to the password string are dropped promptly after
  use. Python strings are immutable so true memory zeroisation is
  not possible at the language level; this is a known limitation of
  Python-based forensic tools.

## Why the existing code didn't work for encrypted Macs

Three gaps, each addressed by one of the changes:

1. `shared/environment.py` (lines 18–37) auto-discovers the user
   Data volume by looking for `.fseventsd` inside mounted APFS
   volumes. A locked FileVault volume is not mounted at all, so this
   discovery silently falls through to `SOURCE_PATH = "/"`.
2. `fuji.py`, `DevicesWindow.on_item_activated` only accepts
   selection for volumes with a mount point. Locked volumes have no
   mount point, so they cannot be selected as a source.
3. There was no FileVault UI, no lock-state reporting, and no unlock
   code path anywhere in the tree.

The initial changes add the missing unlock path — after unlock, the
newly-mounted volume flows through the existing selection logic
naturally. Subsequent bug fixes (see *Bug fixes* section) corrected
three issues that prevented the dialog from appearing and the
recovery-mode launcher from executing.

## `shared/filevault.py` (new)

Pure subprocess wrappers, GUI-free, unit-testable in isolation.

- `EncryptedVolume` dataclass — one per encrypted APFS volume, with
  identifier, name, container reference, APFS roles, FileVault /
  locked booleans, and current mount point. The `is_user_data`
  property is True when `"Data"` is in roles; this is the volume the
  examiner usually wants.
- `list_encrypted_volumes()` — parses `diskutil apfs list -plist`
  using `plistlib`. This is deliberately structured parsing (not
  column-pivot parsing like the existing `_parse_stanza`) because
  lock state is per-volume and needs to be reliable.
- `unlock_volume_readonly(identifier, password)` — the two-step
  unlock flow with the forensic guarantees described above. Returns
  the resulting mount point on success; raises `UnlockError` with
  a sanitised message on any failure. Confirms read-only via
  `verify_readonly` before returning.
- `verify_readonly(mount_point)` — parses `mount(8)` output and
  checks for the `read-only` flag. Used both as a final guard inside
  `unlock_volume_readonly` and by the new check.
- `_classify_unlock_error(stderr, stdout)` — maps diskutil failures
  into user-safe messages ("Incorrect FileVault password.",
  "Volume is not locked.", etc.) without echoing diskutil's raw
  output to the UI.

## `checks/readonly.py` (new)

Implements `ReadOnlySourceCheck`, a standard Fuji check that runs
before acquisition and confirms `PARAMS.source` sits on a read-only
mount. The check is strict: if mount flags can't be determined, it
fails (false negatives are harmless, false positives defeat the
point). The root filesystem case is skipped — in a live OS it's
meaningless, and in Recovery a `source = "/"` means no source has
been selected yet.

The check is wired into `fuji.py`'s `ALL_CHECKS` list so it runs
alongside the existing checks on the overview screen, with the
same visual pass/fail semantics.

## `fuji.py` modifications

All changes are localised to the `DevicesWindow` class and the
module-level imports / `ALL_CHECKS` list. `InputWindow`,
`OverviewWindow`, `ProcessingWindow`, and the main loop are
untouched.

- Module imports: pull in `ReadOnlySourceCheck` and the public
  names from `shared.filevault`.
- `ALL_CHECKS`: `ReadOnlySourceCheck()` added. It runs in all
  modes (live OS and Recovery) — in the live OS `source = "/"`
  is common and the check short-circuits with a pass.
- `DeviceInfo`: two new fields, `filevault_status` (str label)
  and `is_locked` (bool). Defaults preserve the old behaviour
  when no FileVault state is present.
- `DevicesWindow.__init__`: refactored to delegate to two new
  methods, `_enumerate_devices()` and `_populate_list()`, so the
  list can be rebuilt after a successful unlock. The single
  `SetMinSize` call still happens once at init.
- New column `FileVault` inserted between `Device status` and
  `Mount point`. Locked rows render in the accent red rather than
  greyed-out, to distinguish "locked, can be unlocked" from
  "unmounted and unusable".
- `_enumerate_devices()`: the old `df` + `diskutil list` parsing
  block, now with a final overlay step that merges
  `list_encrypted_volumes()` output onto the matching
  `DeviceInfo` rows by identifier. The overlay is wrapped in
  `try/except`: if `diskutil apfs list -plist` fails for any
  reason, the UI degrades to the pre-FileVault behaviour rather
  than erroring out.
- `_populate_list()`: the old row-insertion block, now using the
  two new columns and applying the locked-red colour.
- `_refresh_unlock_button_state()`: enables the unlock button only
  when at least one locked volume is visible.
- `_run_unlock_dialog(preferred_identifier="")`: the core unlock
  helper, extracted from `on_unlock_filevault` to allow both the
  button and a double-click to invoke it. Fetches locked volumes via
  `list_encrypted_volumes()` (which returns `EncryptedVolume`
  objects, as required by `FileVaultUnlockDialog`). If
  `preferred_identifier` is set, that volume is sorted to the front
  of the drop-down. Calls `unlock_volume_readonly`, drops the
  password reference before returning, re-enumerates the list on
  success, and shows an informational dialog with the mount point;
  the examiner then explicitly double-clicks the newly mounted volume
  to set it as the source.
- `on_unlock_filevault(event)`: now a one-line button handler that
  delegates to `_run_unlock_dialog()` with no preferred identifier.
- `FileVaultUnlockDialog`: new modal dialog. `wx.Choice` of locked
  volumes (pre-selecting the `Data` role if present), a
  `wx.TE_PASSWORD` field, Unlock and Cancel buttons. Pressing Enter
  in the password field submits. The dialog has no writable-mount
  option because the forensic contract forbids one.

## Things deliberately not done

- **No recovery-key paths (PRK / IRK).** The spec restricted the
  unlock path to `diskutil apfs unlockVolume` with a passphrase.
  Adding institutional- or personal-recovery-key support would
  require a different diskutil subcommand
  (`-recoveryKeychain`) and a different UI; it's a natural follow-up
  if you need it.
- **No password storage, pre-staging, or "remember me" UI.** The
  password is captured per-unlock, used once, and dropped.
- **No changes to acquisition methods.** Rsync, Ditto, and ASR
  all read from the source; with the source mounted read-only they
  remain compliant. `_create_temporary_image` and related writes
  target the destination / temporary volume, not the source, so
  they are unaffected.
- **No `diskutil repairVolume` or `fsck`.** These were listed as
  forbidden in the forensic constraints. Nothing in the new code
  invokes them, and the existing code does not either.

## Testing

On a Mac running macOS 12+ (Intel or Apple Silicon) booted into
Recovery from a Fuji USB:

1. Launch Fuji; open "List of drives and partitions".
2. The Data volume on the target disk should appear with
   `FileVault: Locked` in the new column and red text. The row is
   now selectable (clicking it will highlight it without bouncing
   focus away).
3. **Either** click "Unlock FileVault volume…" (shows all locked
   volumes in the drop-down), **or** double-click the locked row
   directly (opens the same dialog pre-aimed at that volume).
4. Confirm the volume choice (`Data` role pre-selected), type the
   FileVault password, press Enter or click Unlock.
5. On success, a dialog shows the new mount point under `/Volumes`.
   The device list refreshes; the volume now shows with its mount
   point and `FileVault: Unlocked`.
6. Double-click the (now mounted) volume to set it as the source,
   proceed to the overview screen. `Source read-only check` should
   pass (green).
7. Verify independently with:
   `mount | grep <mount_point>` — expect `read-only` in the flags.
8. Proceed with a Ditto or ASR acquisition as usual.

Wrong-password behaviour: the unlock call fails with "Incorrect
FileVault password." and the volume remains locked; no retry
counter is implemented (diskutil itself does not lock out).

## Bug fixes (April 2026)

Three runtime bugs and one build-time bug were identified and corrected
after initial deployment in Recovery mode.

### 1. Locked volumes could not be selected in the device list (`fuji.py`)

**Root cause.** `DevicesWindow.on_item_focused` only allowed focus to
remain on a row when `device.disk_space and device.disk_space.mount_point`
was truthy. Locked FileVault volumes have no `disk_space` entry (they are
absent from `df` output because they are not mounted), so every click
immediately bounced focus back to the previously selected row.

**Fix.** Added `elif device.is_locked` branch: locked volumes may be
focused and highlighted in the list, giving the examiner visual
confirmation of which volume they are about to unlock.

**Forensic impact.** None. Allowing a row to be highlighted does not
alter the source disk or mount anything.

---

### 2. Double-clicking a locked volume did nothing useful (`fuji.py`)

**Root cause.** `DevicesWindow.on_item_activated` also fell through to
`_back_to_selected()` for any row without a mount point, including locked
volumes. There was no path from double-click to the unlock flow.

**Fix.** Added `elif device.is_locked` branch that calls
`_run_unlock_dialog(preferred_identifier=device.identifier)`. This opens
the unlock dialog pre-aimed at the double-clicked volume, matching the
expectation that double-click = "do the right thing for this row".

**Forensic impact.** None. The dialog still requires an explicit password
entry and a second double-click on the mounted volume to set it as source.

---

### 3. The unlock dialog crashed before appearing — `AttributeError: 'DeviceInfo' object has no attribute 'roles'` (`fuji.py`)

**Root cause.** `_run_unlock_dialog` (and the original `on_unlock_filevault`
before refactoring) built its list of locked volumes from `self.devices`,
which contains `DeviceInfo` objects. `FileVaultUnlockDialog` is typed to
receive `List[EncryptedVolume]` and immediately calls `_format_choice(v)`,
which accesses `v.roles`. `DeviceInfo` has no `roles` attribute, so the
dialog crashed with an `AttributeError` before the password field was
ever rendered.

**Fix.** `_run_unlock_dialog` now calls `list_encrypted_volumes()` directly
to obtain a fresh `List[EncryptedVolume]`, which carries the correct
attributes. The `preferred_identifier` matching still works because both
types use the same disk identifier string (e.g. `disk3s1`).

**Forensic impact.** None. `list_encrypted_volumes()` is read-only
(parses `diskutil apfs list -plist` output). No disk is written.

---

### 4. Recovery-mode launcher script lacked the execute bit (`Fuji.spec` + `shared/environment.py`)

**Root cause.** `Fuji.spec` copies `packaging/Fuji.sh` into the app bundle
as `Fuji` using `shutil.copy`. When the source file resides on an NTFS
(Windows) filesystem, NTFS does not track Unix execute bits, so the copied
script had mode `0o644` — readable but not executable. macOS Launch
Services refused to open the app with "The application 'Fuji' can't be
opened.", and running the binary directly from Terminal confirmed
`Permission denied` on the launcher script.

A secondary failure occurred in `attempt_ramdisk()`: `ditto` faithfully
preserved the missing execute bit when copying the app to the RAM disk,
so the re-launched process from the RAM disk also failed with
`Permission denied`.

**Fix 1 (`Fuji.spec`).** After the `shutil.copy` call, an explicit
`(executable_path / "Fuji").chmod(0o755)` is applied. This ensures every
build sets the correct execute bit regardless of the host filesystem.

**Fix 2 (`shared/environment.py`).** After `ditto` copies the app to the
RAM disk, `ramdisk_launcher.chmod(0o755)` is called as a defence-in-depth
measure. Even if a future build omits the spec fix, the RAM-disk launch
will still succeed.

**Forensic impact.** Both `chmod` calls operate on the tool itself — the
built app bundle and the tool's own volatile RAM disk. Neither the source
disk under examination nor any evidence volume is touched.

---

## Applying the patch

```bash
cd your-fuji-fork
patch -p1 < fuji-filevault.patch
```

Or drop the three files into place directly (new files as-is,
replace `fuji.py`).

No new Python dependencies; `plistlib` is in the standard library.
