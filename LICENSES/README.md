# Package licenses and corresponding source

Every archive retains its upstream license, including its dependencies. This
repository does not relicense Git, mihomo, or any dependency under one common
license. A Portfile's reported identifier can be incomplete or incorrect; inspect
the actual upstream license files and notices.

Per-archive `<archive>.build-info.json` records build provenance. New publications
identify private review inputs with `source_capture_id`; this is not a public
source-download link. Older provenance may contain `source_release_tag`, but that
field alone does not establish that a source release remains available.

Source captures and recipe-license reports remain private. The publisher does not
provide public source bundles or manage a source offer. Maintainers must arrange
any required corresponding-source distribution and notices separately before
publishing binaries. Keep that source available for as long as the applicable
licenses require, even after replacing a binary with a newer version.

Private source capture and signature verification do not establish license
compliance. Original Forge build infrastructure is MIT-licensed; that license
does not apply to the distributed programs or override Apple's macOS/developer-tool
agreements.
