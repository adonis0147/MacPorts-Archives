import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_updates.py"
SPEC = importlib.util.spec_from_file_location("checker", SCRIPT)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)
NOW = datetime(2026, 1, 10, tzinfo=timezone.utc)
EXPECTED = {"darwin": 21, "arch": "x86_64"}


class CheckerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for directory in ("devel/git", "net/mihomo", "devel/dependency", "_resources/port1.0"):
            path = self.root / directory
            path.mkdir(parents=True)
            (path / "recipe").write_text(directory)
        self.baseline = {
            "schema": 1,
            "target": "monterey",
            "platform": ["Darwin", "21.6.0", "x86_64"],
            "specs": [["git"], ["mihomo", "+logging"]],
            "macports_version": "2.11.6",
            "checked_at": NOW.isoformat(),
            "directories": {directory: checker.directory_digest(self.root, directory)
                            for directory in ("devel/git", "net/mihomo", "devel/dependency", "_resources")},
        }

    def check(self, baseline=None, version="2.11.6", now=NOW, target="monterey", expected=None):
        return checker.check(target, expected or EXPECTED,
                             self.baseline if baseline is None else baseline,
                             self.root, version, now)

    def test_unchanged(self):
        self.assertEqual(self.check()[1], [])

    def test_requested_recipe_changes(self):
        for directory in ("devel/git", "net/mihomo"):
            with self.subTest(directory=directory):
                path = self.root / directory / "new-file"
                path.write_text("new content")
                self.assertEqual(self.check()[1], ["requested port recipe changed or removed"])
                path.unlink()

    def test_dependency_and_resources_changes_are_ignored(self):
        fingerprint = self.check()[0]
        for directory in ("devel/dependency", "_resources"):
            with self.subTest(directory=directory):
                (self.root / directory / "new-file").write_text("new content")
                self.assertEqual(self.check(), (fingerprint, []))
        path = self.root / "devel/dependency"
        for file in path.iterdir():
            file.unlink()
        path.rmdir()
        self.assertEqual(self.check(), (fingerprint, []))

    def test_removed_requested_directory(self):
        path = self.root / "devel/git"
        (path / "recipe").unlink()
        path.rmdir()
        self.assertIn("removed", self.check()[1][0])

    def test_missing_or_ambiguous_requested_recipe_mapping(self):
        for directory in ("devel/git", "other/git"):
            with self.subTest(directory=directory):
                baseline = copy.deepcopy(self.baseline)
                if directory == "devel/git":
                    del baseline["directories"][directory]
                else:
                    baseline["directories"][directory] = "0" * 64
                with self.assertRaisesRegex(ValueError, "requested recipe directory for git"):
                    self.check(baseline)

    def test_digest_exact_protocol_and_symlinks(self):
        path = self.root / "test/recipe"
        path.mkdir(parents=True)
        (path / "é.txt").write_bytes(b"bytes\x00")
        (path / "nested").mkdir()
        (path / "nested/file").write_bytes(b"nested")
        (path / "dir-link").symlink_to("../outside", target_is_directory=True)
        (path / "file-link").symlink_to("é.txt")
        records = sorted([
            ["é.txt", "file", hashlib.sha256(b"bytes\x00").hexdigest()],
            ["nested/file", "file", hashlib.sha256(b"nested").hexdigest()],
            ["dir-link", "symlink", "../outside"],
            ["file-link", "symlink", "é.txt"],
        ])
        expected = hashlib.sha256(json.dumps(records, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
        self.assertEqual(checker.directory_digest(self.root, "test/recipe"), expected)
        (path / "dir-link").unlink()
        (path / "dir-link").symlink_to("nested", target_is_directory=True)
        records = [[name, kind, "nested" if name == "dir-link" else value] for name, kind, value in records]
        expected = hashlib.sha256(json.dumps(sorted(records), separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
        self.assertEqual(checker.directory_digest(self.root, "test/recipe"), expected)

    def test_upstream_read_failure_is_not_unchanged(self):
        with patch.object(checker.os, "walk", side_effect=OSError("unreadable checkout")):
            with self.assertRaises(OSError):
                self.check()
        with self.assertRaises(OSError):
            checker.raise_walk_error(OSError("unreadable subdirectory"))

    def test_malicious_paths(self):
        for directory in ("../outside", "devel/..", "./git", "/etc/passwd", "devel/git/files",
                          "devel//git", "devel\\git", "_resources/../outside", "devel/g it", "devel/git\n"):
            with self.subTest(directory=directory):
                baseline = copy.deepcopy(self.baseline)
                baseline["directories"][directory] = "0" * 64
                with self.assertRaises(ValueError):
                    self.check(baseline)
        for directory in ("_resources", "a-b/c+d_1.2"):
            self.assertTrue(checker.valid_directory(directory))

    def test_symlink_ancestors_rejected(self):
        (self.root / "alias").symlink_to(self.root / "devel", target_is_directory=True)
        baseline = copy.deepcopy(self.baseline)
        baseline["directories"]["alias/git"] = baseline["directories"].pop("devel/git")
        with self.assertRaises(ValueError):
            self.check(baseline)

    def test_invalid_baseline_and_target_separation(self):
        for field, value in (("schema", True), ("schema", 2), ("target", "ventura"),
                             ("platform", ["Darwin", "22.0.0", "x86_64"]),
                             ("platform", ["Darwin", "21.0.0", "arm64"]),
                             ("specs", ["git"]), ("directories", {}),
                             ("macports_version", "v2.11.6"), ("checked_at", "2026-01-10")):
            with self.subTest(field=field, value=value):
                baseline = copy.deepcopy(self.baseline)
                baseline[field] = value
                with self.assertRaises(ValueError):
                    self.check(baseline)
        other = copy.deepcopy(self.baseline)
        other.update(target="ventura", platform=["Darwin", "22.0.0", "x86_64"])
        fingerprint = self.check()[0]
        other_fingerprint = self.check(other, target="ventura", expected={"darwin": 22, "arch": "x86_64"})[0]
        self.assertNotEqual(fingerprint, other_fingerprint)
        self.assertFalse(checker.cooling_down({"fingerprint": fingerprint, "dispatched_at": NOW.isoformat()},
                                             other_fingerprint, NOW))

    def test_missing_baseline(self):
        self.assertEqual(checker.check("monterey", EXPECTED, None, self.root, "2.11.6", NOW)[1],
                         ["missing baseline"])

    def test_release_update(self):
        self.assertEqual(self.check(version="2.12.0")[1], ["MacPorts release changed"])

    def test_old_or_missing_timestamp_does_not_force_dispatch(self):
        self.assertEqual(self.check(now=NOW + timedelta(days=30))[1], [])
        del self.baseline["checked_at"]
        self.assertEqual(self.check()[1], [])

    def test_cooldown_exact_boundary_and_new_state(self):
        fingerprint = self.check(version="2.12.0")[0]
        marker = {"fingerprint": fingerprint, "dispatched_at": NOW.isoformat()}
        self.assertTrue(checker.cooling_down(marker, fingerprint, NOW + timedelta(hours=1, microseconds=-1)))
        self.assertFalse(checker.cooling_down(marker, fingerprint, NOW + timedelta(hours=1)))
        self.assertFalse(checker.cooling_down(marker, fingerprint, NOW + timedelta(hours=6)))
        self.assertFalse(checker.cooling_down(marker, "new-state", NOW))
        self.assertFalse(checker.cooling_down(None, fingerprint, NOW))
        self.assertFalse(checker.cooling_down({**marker, "dispatched_at": "bad"}, fingerprint, NOW))
        self.assertEqual(self.check(version="2.12.0", now=NOW + timedelta(days=1))[0], fingerprint)

    def test_downloads_baseline_release_asset(self):
        open_url = Mock(return_value=io.BytesIO(json.dumps(self.baseline).encode()))
        self.assertEqual(checker.download_baseline('owner/Archives', 'monterey', open_url), self.baseline)
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url,
                         'https://github.com/owner/Archives/releases/download/update-baselines/monterey.json')
        self.assertNotIn('Authorization', request.headers)
        with self.assertRaises(ValueError):
            checker.download_baseline('owner/Archives', '../secret', open_url)

    def test_only_missing_assets_are_treated_as_no_baseline(self):
        for status in (403, 404, 500):
            with self.subTest(status=status):
                error = HTTPError('url', status, 'failed', {}, io.BytesIO())
                self.addCleanup(error.close)
                open_url = Mock(side_effect=error)
                if status == 404:
                    self.assertIsNone(checker.download_baseline('owner/Archives', 'monterey', open_url))
                else:
                    with self.assertRaises(HTTPError):
                        checker.download_baseline('owner/Archives', 'monterey', open_url)
        for body in (b'invalid JSON', b'null', b'[]'):
            with self.subTest(body=body), self.assertRaises(ValueError):
                checker.download_baseline('owner/Archives', 'monterey', Mock(return_value=io.BytesIO(body)))
        with self.assertRaises(OSError):
            checker.download_baseline('owner/Archives', 'monterey', Mock(side_effect=OSError('offline')))

    def test_release_lookup(self):
        open_url = Mock(return_value=io.BytesIO(b'{"tag_name":"v2.11.6","prerelease":false}'))
        self.assertEqual(checker.latest_version(open_url), "2.11.6")
        for release in ({"tag_name": "v2.12.0-rc1"}, {"tag_name": "v2.12.0", "prerelease": True}):
            with self.assertRaises(ValueError):
                checker.latest_version(Mock(return_value=io.BytesIO(json.dumps(release).encode())))
        with self.assertRaises(OSError):
            checker.latest_version(Mock(side_effect=OSError("upstream unavailable")))

    def test_dispatch_interface(self):
        run = Mock()
        with patch.dict(os.environ, {"FORGE_DISPATCH_TOKEN": "secret", "FORGE_REPOSITORY": "owner/forge",
                                     "FORGE_REF": "stable"}):
            checker.dispatch("monterey", run)
        args, kwargs = run.call_args
        self.assertIn("repos/owner/forge/actions/workflows/build-ports.yml/dispatches", args[0])
        self.assertEqual(json.loads(kwargs["input"]), {"ref": "stable", "inputs": {"macos": "monterey"}})
        self.assertTrue(kwargs["check"])
        self.assertEqual(kwargs["env"]["GH_TOKEN"], "secret")
        self.assertNotIn("secret", str(args))

    def test_main_saves_only_success_and_obeys_cooldown(self):
        targets = self.root / "targets.json"
        targets.write_text(json.dumps({"monterey": EXPECTED}))
        state = self.root / "state.json"
        output = self.root / "output"
        argv = [str(SCRIPT), "--ports", str(self.root), "--targets", str(targets),
                "--repository", "owner/Archives", "--state", str(state)]
        with patch.object(checker.sys, "argv", argv), patch.object(checker, "latest_version", return_value="2.11.6"), \
                patch.object(checker, "download_baseline", return_value=None) as download, \
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}), patch.object(checker, "dispatch") as dispatch:
            dispatch.side_effect = subprocess.CalledProcessError(1, "gh")
            with self.assertRaises(subprocess.CalledProcessError):
                checker.main()
            self.assertFalse(state.exists())
            self.assertFalse(output.exists())
            dispatch.side_effect = None
            checker.main()
            self.assertTrue(state.exists())
            self.assertEqual(output.read_text(), "dispatched=true\n")
            dispatch.reset_mock()
            checker.main()
            dispatch.assert_not_called()
            download.assert_called_with('owner/Archives', 'monterey')
            download.side_effect = OSError('baseline unavailable')
            with self.assertRaises(OSError):
                checker.main()
            dispatch.assert_not_called()
        with patch.object(checker.sys, "argv", argv), \
                patch.object(checker, "latest_version", side_effect=OSError("offline")), \
                patch.object(checker, "dispatch") as dispatch:
            with self.assertRaises(OSError):
                checker.main()
            dispatch.assert_not_called()

    def test_partial_dispatch_failure_keeps_only_successful_marker(self):
        targets = self.root / "targets.json"
        targets.write_text(json.dumps({"monterey": EXPECTED, "ventura": {"darwin": 22, "arch": "x86_64"}}))
        state = self.root / "state.json"
        output = self.root / "output"
        argv = [str(SCRIPT), "--ports", str(self.root), "--targets", str(targets),
                "--repository", "owner/Archives", "--state", str(state)]
        with patch.object(checker.sys, "argv", argv), patch.object(checker, "latest_version", return_value="2.11.6"), \
                patch.object(checker, "download_baseline", return_value=None), \
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}), \
                patch.object(checker, "dispatch", side_effect=[None, subprocess.CalledProcessError(1, "gh")]) as dispatch:
            with self.assertRaises(subprocess.CalledProcessError):
                checker.main()
            self.assertEqual([call.args[0] for call in dispatch.call_args_list], ["monterey", "ventura"])
            self.assertEqual(set(json.loads(state.read_text())), {"monterey"})
            self.assertEqual(output.read_text(), "dispatched=true\n")

    def test_workflow_is_the_public_default_branch_scheduler(self):
        workflow = (SCRIPT.parents[1] / '.github/workflows/check-updates.yml').read_text()
        self.assertIn('cron: "43 5,11,17,23 * * *"', workflow)
        self.assertIn('  workflow_dispatch:', workflow)
        self.assertNotIn('  push:', workflow)
        self.assertNotIn('  pull_request:', workflow)
        self.assertIn("if: github.ref == format('refs/heads/{0}', github.event.repository.default_branch)", workflow)
        self.assertIn('persist-credentials: false', workflow)
        self.assertIn('FORGE_DISPATCH_TOKEN: ${{ secrets.FORGE_DISPATCH_TOKEN }}', workflow)
        self.assertIn("if: ${{ !cancelled() && steps.check.outputs.dispatched == 'true' }}", workflow)

    def test_target_config_validation(self):
        path = self.root / "targets.json"
        for targets in ({"../escape": EXPECTED}, {"monterey": {"darwin": True, "arch": "x86_64"}}, {}):
            path.write_text(json.dumps(targets))
            with self.assertRaises(ValueError):
                checker.load_targets(path)


if __name__ == "__main__":
    unittest.main()
