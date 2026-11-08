# MacPorts-Archives

Unofficial MacPorts binary archives, signatures, checksums and build provenance.
See [Releases](https://github.com/adonis0147/MacPorts-Archives/releases) for available
builds; this repository does not promise an archive until it appears there.
Initial build targets are Intel macOS 12 (Monterey), including `git` and
`mihomo +logging`. Nothing here is an official MacPorts release or endorsement.

## Release layout

- A tag named after each port (`git`, `mihomo`, and dependency names) holds original
  MacPorts `.tbz2` filenames, `.rmd160` signatures, `.sha256` files and per-archive
  `.build-info.json` provenance. Versions, variants and architectures stay encoded
  in MacPorts' filenames; existing assets are not overwritten with different bytes.
- `signing-key` holds the public `macports-forge.pem` key.
- Source-review bundles remain private; this publisher does not create `source-*`
  releases. New per-archive provenance records a private `source_capture_id`, not a
  public source-download link.
- VM disks, private signing keys and credentials are never published here.

## Configure MacPorts

### 1. Review the trust boundary

Use a normal `/opt/local` MacPorts installation for the matching macOS version and
architecture. Port version, revision and variants must match a published archive.
Installing a public key grants **system-wide archive trust**, not trust limited to
this site or these two ports. Only continue if you trust this maintainer.

### 2. Authenticate the public key

Download the key without installing it yet:

```sh
curl --fail --location --output macports-forge.pem \
  https://github.com/adonis0147/MacPorts-Archives/releases/download/signing-key/macports-forge.pem
shasum -a 256 macports-forge.pem
```

The current key's **PEM SHA-256**, published in this repository's history, is:

```text
50682d774720a10a9be8c86e35837b5dbe540c277864bf7c37034512299149da
```

Authenticate this repository/maintainer before trusting that fingerprint. It is
not an SSH key fingerprint, and a checksum downloaded next to a key is not by
itself proof of authenticity. Future publishing runs also report this fingerprint
in their private workflow summary. A different key requires explicit rotation,
not silently replacing the release key or documented fingerprint.

After verification:

```sh
sudo install -m 644 macports-forge.pem /opt/local/share/macports/macports-forge.pem
```

Append this path to `/opt/local/etc/macports/pubkeys.conf`, preserving official keys:

```text
/opt/local/share/macports/macports-forge.pem
```

### 3. Add the archive site

Append the contents of this repository's [`archive_sites.conf`](archive_sites.conf)
to `/opt/local/etc/macports/archive_sites.conf`. Do not replace existing settings
or confuse this file with `sources.conf`, which configures Portfile sources.
Add the site once, not on every installation.

The base URL deliberately ends at `/releases/download/`: MacPorts appends the port
name and exact filename, resolving to `/releases/download/git/<filename>`, for
example. Prefix, applications/framework paths, C++ library and `.la` policy must
match the configured site or MacPorts will filter it out.

### 4. Prefer this archive site (optional)

MacPorts sorts mirrors by latency, not their order in `archive_sites.conf`.
To try GitHub before the official mirrors, add this to
`/opt/local/etc/macports/macports.conf`:

```text
preferred_hosts github.com
```

If an active `preferred_hosts` line already exists, append `github.com` to that
line once, preserving other hosts. This setting matches hostnames only, not URL
paths such as `github.com/adonis0147`; it also affects other configured GitHub
sources. The archive-site URL above restricts this source to MacPorts-Archives.
Official mirrors remain enabled as fallbacks, including for dependencies.

### 5. Install matching packages

```sh
sudo port -v -b install git
sudo port -v -b install mihomo +logging
```

`-b` forbids a silent source-build fallback. Official binary sites remain available,
so this flag alone does not prove this repository supplied the archive. Inspect
verbose fetch output for this repository's GitHub release URL to confirm the origin.

A newer Portfile revision or different variants may have no matching archive yet.
Do not rename an old archive to make it fit. Existing installations can also bypass
a download, so test on a clean installation when validating availability.

## Public update checks

[Check upstream updates](.github/workflows/check-updates.yml) runs on Ubuntu at
05:43, 11:43, 17:43 and 23:43 UTC daily, or manually **on the default branch**.
There are no push/PR triggers, VMs, private repository checkouts or private
baseline downloads. Each run checks out the latest public default branch, shallow
clones the default branch of `macports/macports-ports`, and queries the latest
stable GitHub release of `macports/macports-base` (removing a leading `v`). An
upstream lookup failure fails the run; it never means “unchanged.” The checker
reads files as data and never executes upstream recipes.

[`config/targets.json`](config/targets.json) maps target codenames to their expected
Darwin major and architecture. Initially only `monterey` (Darwin 21, `x86_64`) is
enabled. Add targets there, not separate workflows. Each target uses its own
`updates/<target>.json` public baseline, produced by Forge **only after successful
publication or a successful VM comparison against the last published plan**. A missing baseline requests a build. Changed or removed tracked
recipes (including dependencies), changed shared resources, or a different stable
MacPorts version also request one. An invalid baseline fails closed instead of
silently comparing the wrong target.

### Maintainer setup and security

1. Create a fine-grained token restricted to **only the private Forge repository**,
   with **Actions: read and write** and the required **Metadata: read** permission. Store it
   here as the Actions secret `FORGE_DISPATCH_TOKEN`. Do not grant contents access
   or use a broadly scoped classic PAT. The token is used only for dispatch, never
   for checkout, upstream lookup or cache storage.
2. Optionally set repository variables `FORGE_REPOSITORY` (default
   `adonis0147/MacPorts-Forge`) and `FORGE_REF` (default `main`). The selected Forge
   ref must expose `build-ports.yml` with a `workflow_dispatch` input named `macos`.
   The request is `{"ref":"main","inputs":{"macos":"monterey"}}`. GitHub must
   recognize that workflow on Forge's default branch for dispatch to work.
3. Have Forge publish the baseline protocol below to this repository's default
   branch after publication or a successful unchanged-plan comparison. Forge's publishing credentials stay private; the
   public workflow's built-in `GITHUB_TOKEN` has only `contents: read`.
4. Enable Actions and scheduled workflows here. Run manually from the default
   branch to initialize a missing baseline. Review changes to the checker and
   workflow as privileged code: they can use the dispatch secret. Dispatch does
   not give public jobs access to Forge contents, signing keys or guest VMs.

One concurrency group serializes scheduled/manual runs without cancelling active
checks. Actions cache restore/save uses the normal Actions cache runtime token;
no `actions: write` grant to this repository's `GITHUB_TOKEN` is needed.

### Weekly safety and retries

Forge refreshes `checked_at` after successful publication or a successful VM
comparison confirming that the plan matches the last successfully published plan.
That comparison acknowledges harmless recipe changes without advancing the
published package plan. If that UTC timestamp is at least seven days old,
a full build is requested as a safety check (for inputs not captured by recipe
hashes). Missing `checked_at` is also immediately due; malformed timestamps fail.
This is a seven-day age check, not a calendar-week bucket.

Successful **dispatches**, not successful builds, are recorded in a public Actions
cache marker containing each target's requested-state fingerprint and dispatch
time. The fingerprint covers target identity, baseline, current tracked directory
digests and current MacPorts version. An identical state is suppressed for less
than 24 hours; failed builds are therefore retried after 24 hours while the
baseline remains stale. Changed state can dispatch immediately. No marker is
written for a failed dispatch. If one target succeeds and another fails, the
successful marker is still saved. A successful dispatch does not itself advance
the public baseline or its `checked_at` timestamp.

Cache markers are best-effort deduplication, not a durable queue: eviction, cache
outages or a cancellation between dispatch and save can cause an extra build.
Cache contents are public, contain no credentials, and must not be treated as
proof of publication. GitHub may delay schedules or disable them for inactivity;
weekly checks depend on this workflow continuing to run.

### Baseline protocol (schema 1)

Example shape (replace placeholder digests with real lowercase SHA-256 values):

```json
{
  "schema": 1,
  "target": "monterey",
  "platform": ["Darwin", "21.6.0", "x86_64"],
  "specs": [["git"], ["mihomo", "+logging"]],
  "macports_version": "2.11.6",
  "checked_at": "2026-01-10T12:00:00Z",
  "directories": {
    "devel/git": "<64 lowercase hex characters>",
    "devel/dependency-recipe": "<64 lowercase hex characters>",
    "_resources": "<64 lowercase hex characters>"
  }
}
```

- `target` must match the filename/config codename. `platform` must be exactly
  `["Darwin", "<major>.<minor>.<patch>", "<arch>"]`, matching the configured major
  and architecture. `macports_version` is the installed numeric `x.y.z` version.
- `specs` is a nonempty list of lists: port name first, then individual signed
  variant tokens such as `+logging` (negative variants are also accepted). These
  describe Forge's requested ports; the public checker does not resolve dependencies.
- `directories` must include **every recipe directory used by the build, including
  transitive dependencies**, plus the **entire `_resources` tree**. Forge resolves
  that closure; the public checker compares exactly those directories. Newly
  introduced dependencies are discovered when Forge rebuilds a changed recipe.
- Directory keys are upstream-root-relative POSIX paths: exactly `category/name`
  or `_resources`. Each component allows only ASCII letters, numbers, `_`, `.`,
  `+`, `-`; components `.` and `..` are forbidden. Absolute paths, backslashes,
  extra levels and symlinked directory roots/ancestors are rejected.
- For each directory, recursively collect all files and symlinks, including hidden
  files. Paths in records are POSIX paths **relative to that directory**, not the
  ports-tree root. A regular-file record is
  `[relative_path, "file", sha256(file_bytes).hexdigest()]`; a symlink record is
  `[relative_path, "symlink", symlink_target]`. Include symlinked directories as
  symlinks and do not descend into them. Do not hash empty directories, modes or
  mtimes. There is no `.git` exclusion inside recipe directories (none is expected).
- Sort the list of records lexicographically, then compute exactly:

  ```python
  hashlib.sha256(
      json.dumps(sorted(records), separators=(",", ":"), ensure_ascii=True).encode()
  ).hexdigest()
  ```

- `checked_at` is an ISO UTC timestamp (`Z` or `+00:00`), representing the last
  successful publication or full VM check against the published plan, never merely
  a public polling run.
  Older schema-1 producers may omit it, which makes the weekly safety check due.

### Local validation

No dependencies are needed beyond Python 3.9+ (the workflow also uses runner-provided
Git and GitHub CLI). Tests use temporary trees and mocked release/dispatch calls:

```sh
python3 -m unittest discover -s tests -v
prettier --check README.md .github/workflows/check-updates.yml config/targets.json
```

The script interface is `python3 scripts/check_updates.py --ports <local-ports-tree>`;
optional `--targets`, `--baselines` and `--state` default to `config/targets.json`,
`updates` and `.update-state/state.json`. **Running the script is not a dry run:** it queries the public release
API and may dispatch Forge using `FORGE_DISPATCH_TOKEN`. Tests do neither. Unit tests
do not establish live GitHub cache, token, dispatch or macOS build success.

## Checksums, source and licensing

MacPorts verifies `.rmd160` signatures using configured trusted public keys.
Standalone `.sha256` files offer additional integrity checks but do not substitute
for authenticating the signing key.

Source inputs and license-review bundles are captured privately, not published
as release assets. A private capture ID is not a public source offer. Maintainers
must arrange any required corresponding-source distribution and notices separately
before distributing binaries; private capture alone does not establish compliance.

Each package retains its own license. Recipe license strings are informational,
not a replacement for actual upstream license terms. See [LICENSES](LICENSES/README.md)
and the upstream license files. There is no blanket MIT license for the binaries.
Original Forge build recipes are MIT-licensed.

A local Monterey installation downloaded and activated the published Git archive.
This does not establish clean-machine compatibility or success for other ports,
variants or macOS versions. There is no automatic clean-consumer verification
workflow; release assets determine current availability.
