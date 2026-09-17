#!/usr/bin/env python3
"""
Tests for the helper scripts in tests/. Stdlib only.

These scripts are what a developer runs before pushing, so the properties that matter are boring
ones: they exist, they are executable, they fail loudly (`set -euo pipefail`), and — the one that
actually rots — they do not hardcode the variant matrix, which lives in the publish workflow.
"""
import os
import shutil
import stat
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = ["tests/build-matrix.sh", "tests/run-all.sh", "tests/smoke.sh", "tests/gpu.sh"]


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


class TestShellScripts(unittest.TestCase):
    def test_they_exist_and_are_executable(self):
        for rel in SCRIPTS:
            path = os.path.join(ROOT, rel)
            self.assertTrue(os.path.isfile(path), f"{rel} missing")
            self.assertTrue(os.stat(path).st_mode & stat.S_IXUSR, f"{rel} is not executable")

    def test_they_have_a_bash_shebang(self):
        for rel in SCRIPTS:
            self.assertTrue(read(rel).startswith("#!/usr/bin/env bash"), f"{rel}: wrong shebang")

    def test_they_fail_loudly(self):
        for rel in SCRIPTS:
            self.assertIn("set -euo pipefail", read(rel), f"{rel}: missing strict mode")

    @unittest.skipUnless(shutil.which("shellcheck"), "shellcheck not installed")
    def test_shellcheck_is_clean(self):
        res = subprocess.run(["shellcheck", *SCRIPTS], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)


class TestBuildMatrixScript(unittest.TestCase):
    def test_it_does_not_hardcode_the_matrix(self):
        # The variants live in docker-publish.yml. A second copy here would drift on the next bump,
        # and a build script that tests the wrong versions is worse than no build script.
        body = read("tests/build-matrix.sh")
        self.assertIn("docker-publish.yml", body)
        for hardcoded in ("sdk/12.1", "sdk/11.0"):
            self.assertNotIn(hardcoded, body, "the sdk branch is hardcoded instead of read from the workflow")

    def test_it_runs_the_smoke_test_for_each_variant(self):
        self.assertIn("smoke.sh", read("tests/build-matrix.sh"))

    def test_usage_without_docker_or_with_help_does_not_build(self):
        res = subprocess.run(["tests/build-matrix.sh", "--help"], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("usage", (res.stdout + res.stderr).lower())


class TestRunAllScript(unittest.TestCase):
    def test_it_covers_every_local_gate(self):
        body = read("tests/run-all.sh")
        for gate in ("unittest", "backlog-lint.py", "generate-roadmap.py --check",
                     "site/build.py --check", "shellcheck"):
            self.assertIn(gate, body, f"run-all.sh does not run {gate}")

    def test_it_does_not_build_images(self):
        # run-all.sh is the fast gate: no docker, that is build-matrix.sh's job.
        self.assertNotIn("docker build", read("tests/run-all.sh"))


class TestVariantsCli(unittest.TestCase):
    """`site/build.py --print-variants` is what the shell scripts read the matrix through."""

    def test_it_prints_one_line_per_variant(self):
        res = subprocess.run(["python3", "site/build.py", "--print-variants"],
                             cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        lines = [l for l in res.stdout.strip().split("\n") if l]
        self.assertGreaterEqual(len(lines), 3)
        for line in lines:
            version, branch, is_default = line.split()
            self.assertRegex(version, r"^\d+\.\d+(\.\d+)?$")
            self.assertTrue(branch.startswith("sdk/"), branch)
            self.assertIn(is_default, ("default", "-"))

    def test_exactly_one_default(self):
        res = subprocess.run(["python3", "site/build.py", "--print-variants"],
                             cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(sum(1 for l in res.stdout.split("\n") if l.endswith("default")), 1)


if __name__ == "__main__":
    unittest.main()
