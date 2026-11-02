# Package licenses and corresponding source

Every archive retains its upstream license, including its dependencies. This
repository does not relicense Git, mihomo, or any dependency under one common
license. A Portfile's reported identifier can be incomplete or incorrect; inspect
the upstream license files in the captured source as well.

For each binary:

1. Read its adjacent `<archive>.build-info.json` for the exact recipe/build metadata
   and `source_release_tag`.
2. Open that `source-*` release and download its source parts and `SHA256SUMS`.
3. Check the hashes, reconstruct the source archive, and inspect the original source
   distributions, Portfiles/patches, retained build inputs and upstream notices.
4. The `license-report.json` describes captured recipe metadata and explicitly
   requires package-specific license review. `forge-LICENSE.txt` applies only to
   original Forge build infrastructure, not to the distributed programs.

Corresponding-source releases must remain available while their binaries are
redistributed and for any additional period required by their licenses. New
versions do not justify deleting older source material. Capturing a source tree
alone does not automatically establish compliance with every license or Apple's
macOS/developer-tool agreements.
