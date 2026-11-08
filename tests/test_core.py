"""Tests run against a temporary HOME and global git config; the real ~/.gitconfig is never touched."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="gitacct-test-"))
os.environ["GITACCOUNTS_HOME"] = str(TMP / "home")
os.environ["GIT_CONFIG_GLOBAL"] = str(TMP / "home" / ".gitconfig")
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
(TMP / "home").mkdir()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gitaccounts import core  # noqa: E402

WORK = core.Profile("work", "Work", "alex-at-work", "alex@corp.example", "alex-at-work", color="#b7791f")
PERS = core.Profile("personal", "Personal", "Alex Personal", "123+alex@users.noreply.github.com", "alex-personal")


def sh(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def make_repo(name, commits=0, as_=WORK):
    d = TMP / name
    d.mkdir(parents=True)
    sh("init", "-q", "-b", "main", cwd=d)
    for i in range(commits):
        (d / f"f{i}.txt").write_text(str(i))
        sh("add", "-A", cwd=d)
        sh("-c", f"user.name={as_.name}", "-c", f"user.email={as_.email}", "commit", "-q", "-m", f"c{i}",
           "--date", f"2026-01-0{i + 1}T10:00:00", cwd=d)
    return d


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sh("config", "--global", "user.name", WORK.name, cwd=TMP)
        sh("config", "--global", "user.email", WORK.email, cwd=TMP)

    def store(self):
        s = core.Store([core.Profile(**vars(WORK)), core.Profile(**vars(PERS))])
        s.save()
        return s

    def test_seed_from_global(self):
        p = core.detect_global_profile()
        self.assertEqual((p.id, p.email, p.github_user), ("work", WORK.email, "alex-at-work"))

    def test_validation(self):
        bad = [dict(id="Bad Id"), dict(email="nope"), dict(name='a"b'), dict(github_user="x y"),
               dict(ssh_key=str(TMP / "missing"))]
        for change in bad:
            with self.assertRaises(ValueError, msg=change):
                core.Profile(**{**vars(PERS), **change}).validate()

    def test_status_global_then_use_and_clear(self):
        s = self.store()
        d = make_repo("r_use")
        st = core.status(str(d), s)
        self.assertEqual(st["profile"], "work")
        self.assertTrue(st["identity_source"].startswith("global"))
        core.use_profile(str(d), s.get("personal"))
        st = core.status(str(d), s)
        self.assertEqual(st["profile"], "personal")
        self.assertTrue(st["identity_source"].startswith("local"))
        self.assertEqual(sh("config", "--local", "credential.username", cwd=d), "alex-personal")
        core.clear_repo_profile(str(d))
        self.assertEqual(core.status(str(d), s)["profile"], "work")

    def test_commit_refuses_wrong_identity(self):
        s = self.store()
        d = make_repo("r_commit")
        (d / "a.txt").write_text("x")
        with self.assertRaises(core.GitError):
            core.commit_all(str(d), "msg", s.get("personal"))
        core.use_profile(str(d), s.get("personal"))
        out = core.commit_all(str(d), "first", s.get("personal"))
        self.assertIn(PERS.email, out)
        self.assertEqual(sh("log", "-1", "--format=%ae|%ce", cwd=d), f"{PERS.email}|{PERS.email}")

    def test_init_repo_pins_profile(self):
        s = self.store()
        d = TMP / "r_init"
        core.init_repo(str(d), s.get("personal"))
        self.assertEqual(sh("config", "--local", "gitaccounts.profile", cwd=d), "personal")
        self.assertEqual(sh("branch", "--show-current", cwd=d), "main")

    def test_folder_rules_apply_and_replace(self):
        s = self.store()
        root = TMP / "personal_area"
        d = make_repo("personal_area/proj")
        other = make_repo("work_area/proj")
        s.rules = [core.Rule(core.fwd(root), "personal")]
        s.save()
        core.apply_rules(s)
        core.apply_rules(s)  # idempotent: no duplicate entries
        entries = sh("config", "--global", "--get-regexp", "includeif", cwd=TMP).splitlines()
        self.assertEqual(len(entries), 1)
        st = core.status(str(d), s)
        self.assertEqual(st["profile"], "personal")
        self.assertIn("personal.gitconfig", st["identity_source"])
        self.assertEqual(core.status(str(other), s)["profile"], "work")
        self.assertEqual(core.matching_rule(str(d), s).profile_id, "personal")
        s.rules = []
        core.apply_rules(s)
        self.assertEqual(sh("config", "--global", "--get-regexp", "includeif", cwd=TMP) if
                         subprocess.run(["git", "config", "--global", "--get-regexp", "includeif"],
                                        capture_output=True).returncode == 0 else "", "")
        self.assertEqual(core.status(str(d), s)["profile"], "work")
        # user's own (unmanaged) includeIf entries are preserved
        sh("config", "--global", "includeIf.gitdir:C:/x/.path", "C:/elsewhere.gitconfig", cwd=TMP)
        core.apply_rules(s)
        self.assertIn("elsewhere", sh("config", "--global", "--get-regexp", "includeif", cwd=TMP))
        sh("config", "--global", "--unset", "includeIf.gitdir:C:/x/.path", cwd=TMP)

    def test_reauthor_only_unpushed_and_keeps_dates(self):
        s = self.store()
        d = make_repo("r_reauthor", commits=3)
        bare = TMP / "r_reauthor_remote.git"
        sh("init", "-q", "--bare", str(bare), cwd=TMP)
        sh("remote", "add", "origin", str(bare), cwd=d)
        first = sh("rev-list", "--max-parents=0", "HEAD", cwd=d)
        sh("push", "-q", "origin", f"{first}:refs/heads/main", cwd=d)
        sh("fetch", "-q", "origin", cwd=d)
        dates_before = sh("log", "--format=%ad", "--date=iso", cwd=d).splitlines()
        self.assertEqual(len(core.unpushed_commits(str(d))), 2)
        n = core.reauthor_unpushed(str(d), s.get("personal"))
        self.assertEqual(n, 2)
        log = sh("log", "--format=%ae|%ce|%s", cwd=d).splitlines()
        self.assertEqual(log[0], f"{PERS.email}|{PERS.email}|c2")
        self.assertEqual(log[1], f"{PERS.email}|{PERS.email}|c1")
        self.assertEqual(log[2], f"{WORK.email}|{WORK.email}|c0")  # pushed commit untouched
        self.assertEqual(sh("log", "--format=%ad", "--date=iso", cwd=d).splitlines(), dates_before)
        self.assertEqual(sh("rev-list", "--max-parents=0", "HEAD", cwd=d), first)
        self.assertTrue(sh("for-each-ref", "refs/gitaccounts/backup", cwd=d))

    def test_reauthor_root_when_nothing_pushed(self):
        s = self.store()
        d = make_repo("r_root", commits=2)
        self.assertEqual(core.reauthor_unpushed(str(d), s.get("personal")), 2)
        self.assertEqual(set(sh("log", "--format=%ae", cwd=d).splitlines()), {PERS.email})

    def test_reauthor_refuses_dirty_tree(self):
        s = self.store()
        d = make_repo("r_dirty", commits=1)
        (d / "f0.txt").write_text("changed")
        with self.assertRaises(core.GitError):
            core.reauthor_unpushed(str(d), s.get("personal"))

    def test_push_to_local_remote_and_guard(self):
        s = self.store()
        d = make_repo("r_push", commits=1)
        bare = TMP / "r_push_remote.git"
        sh("init", "-q", "--bare", str(bare), cwd=TMP)
        sh("remote", "add", "origin", str(bare), cwd=d)
        with self.assertRaises(core.GitError):
            core.push(str(d), s.get("personal"))  # repo identity is work
        core.use_profile(str(d), s.get("work"))
        core.push(str(d), s.get("work"))
        self.assertEqual(sh("rev-parse", "main", cwd=bare), sh("rev-parse", "HEAD", cwd=d))
        self.assertEqual(core.unpushed_commits(str(d)), [])

    def test_set_remote_validation(self):
        d = make_repo("r_remote", commits=1)
        core.set_remote(str(d), "git@github.com:alex-personal/repo.git")
        core.set_remote(str(d), "https://github.com/alex-personal/repo.git")
        self.assertEqual(sh("remote", "get-url", "origin", cwd=d), "https://github.com/alex-personal/repo.git")
        for bad in ("rm -rf /", "C:/x", "git@github.com:me;evil"):
            with self.assertRaises(core.GitError):
                core.set_remote(str(d), bad)

    def test_generate_key_and_ssh_command(self):
        p = core.Profile(**vars(PERS))
        key = core.generate_key(p)
        p.ssh_key = str(key)
        p.validate()
        self.assertTrue(core.public_key(p).startswith("ssh-ed25519 "))
        self.assertIn(PERS.email, core.public_key(p))
        with self.assertRaises(core.GitError):
            core.generate_key(p)  # never overwrites
        s = core.Store([p])
        d = make_repo("r_key")
        core.use_profile(str(d), p)
        self.assertIn("IdentitiesOnly=yes", sh("config", "--local", "core.sshCommand", cwd=d))
        inc = core.write_include(p).read_text()
        self.assertIn("sshCommand", inc)
        s.save()
        self.assertEqual(core.load().get("personal").ssh_key, str(key))


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
