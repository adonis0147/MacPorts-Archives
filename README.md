# MacPorts-Archives

Unofficial MacPorts binary archives, signatures, checksums and corresponding source.
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
- `source-*` releases hold source bundles, checksums, build metadata and license
  reports. Each binary's `.build-info.json` identifies its corresponding source tag.
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

### 4. Install matching packages

```sh
sudo port -b install git
sudo port -b install mihomo +logging
```

`-b` forbids a silent source-build fallback. Official binary sites remain available,
so this flag alone does not prove this repository supplied the archive. Inspect
verbose fetch output if origin matters. The Forge clean-consumer workflow disables
all other sites to test this server specifically.

A newer Portfile revision or different variants may have no matching archive yet.
Do not rename an old archive to make it fit. Existing installations can also bypass
a download, so test on a clean installation when validating availability.

## Checksums, source and licensing

MacPorts verifies `.rmd160` signatures using configured trusted public keys.
Standalone `.sha256` files offer additional integrity checks but do not substitute
for authenticating the signing key.

Source releases include original fetched inputs, frozen Portfiles/patches/PortGroups,
retained work/module caches, build configuration and recipe scripts. To reconstruct
a split source download, download **all assets** from its source release into a
new directory (the checksum manifest also covers metadata and license reports):

```sh
shasum -a 256 --check SHA256SUMS
cat source.tar.gz.part* > source.tar.gz
```

Inspect the result before extracting into a new non-root directory; never use
`sudo tar` on an uninspected source bundle.

Each package retains its own license. Recipe license strings are informational,
not a replacement for actual upstream license terms. See [LICENSES](LICENSES/README.md)
and the source release's report and upstream license files. There is no blanket
MIT license for the binaries. Original Forge build recipes are MIT-licensed.

Only bare Monterey boot/SSH was previously live-tested. The new complete package
publication and clean-consumer pipeline is not yet live-validated; release assets
and their workflow results determine availability.
