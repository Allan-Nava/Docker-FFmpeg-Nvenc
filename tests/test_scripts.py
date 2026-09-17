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
import tempfile
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = ["tests/build-matrix.sh", "tests/run-all.sh", "tests/smoke.sh", "tests/gpu.sh",
           "docs/scripts/commit.sh", "docs/scripts/install-hooks.sh", ".githooks/commit-msg"]


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


class TestCommitAutomation(unittest.TestCase):
    """One command for "commit + changelog", and a hook that keeps the subject parseable."""

    def test_commit_script_runs_the_gates_and_files_the_changelog(self):
        body = read("docs/scripts/commit.sh")
        self.assertIn("run-all.sh", body)
        self.assertIn("changelog-add.py", body)
        self.assertIn("git commit", body)

    def test_commit_script_can_skip_the_slow_gates_explicitly(self):
        self.assertIn("--no-gates", read("docs/scripts/commit.sh"))

    def test_commit_script_help_exits_zero(self):
        res = subprocess.run(["docs/scripts/commit.sh", "--help"], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("usage", (res.stdout + res.stderr).lower())

    def test_install_hooks_points_git_at_the_tracked_hooks(self):
        body = read("docs/scripts/install-hooks.sh")
        self.assertIn("core.hooksPath", body)
        self.assertIn(".githooks", body)

    def test_hook_validates_through_the_shared_library(self):
        # The rule lives in docs/scripts/lib/changelog.py; a second copy in bash would drift.
        body = read(".githooks/commit-msg")
        self.assertIn("changelog", body)
        self.assertNotIn("^feat|^fix", body, "the conventional-commit regex is duplicated in the hook")

    def _hook(self, message, tmp):
        path = os.path.join(tmp, "MSG")
        with open(path, "w", encoding="utf-8") as f:
            f.write(message)
        return subprocess.run([os.path.join(ROOT, ".githooks/commit-msg"), path],
                              cwd=ROOT, text=True, capture_output=True)

    def test_hook_accepts_a_conventional_subject(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._hook("feat: add a variant\n", tmp).returncode, 0)

    def test_hook_accepts_the_release_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._hook("release: v2.0.0\n", tmp).returncode, 0)

    def test_hook_rejects_a_free_form_subject(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = self._hook("fixed some stuff\n", tmp)
            self.assertEqual(res.returncode, 1)
            self.assertIn("conventional", (res.stdout + res.stderr).lower())

    def test_hook_ignores_comment_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            msg = "# please enter the commit message\nfeat: real subject\n"
            self.assertEqual(self._hook(msg, tmp).returncode, 0)


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
