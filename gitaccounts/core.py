"""Git/GitHub account profiles: per-repo identity, folder rules, SSH keys, safe git actions.

Everything here shells out to `git` / `ssh` and never stores secrets. Profiles live in
~/.gitaccounts/profiles.json (home dir, not AppData, so it is the same file no matter which
app launches the tool).
"""
import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
HOME = Path(os.environ.get("GITACCOUNTS_HOME") or Path.home())
CONFIG_DIR = HOME / ".gitaccounts"
PROFILES_FILE = CONFIG_DIR / "profiles.json"
SSH_DIR = HOME / ".ssh"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
SAFE_TEXT_RE = re.compile(r'^[^"`$\\<>\n\r]+$')
EMAIL_RE = re.compile(r"^[^@\s<>\"]+@[^@\s<>\"]+$")
MANAGED_KEYS = ("user.name", "user.email", "core.sshCommand", "credential.username", "gitaccounts.profile")

# command log: every git/ssh command run, for the GUI's transparency panel
LOG: list[str] = []
_listeners = []


def on_log(fn):
    _listeners.append(fn)


def _log(line: str):
    LOG.append(line)
    for fn in _listeners:
        try:
            fn(line)
        except Exception:
            pass


class GitError(RuntimeError):
    pass


def run(args: list[str], cwd=None, check=True, env=None, timeout=120) -> subprocess.CompletedProcess:
    shown = " ".join(a if " " not in a else f'"{a}"' for a in args)
    _log(f"$ {shown}" + (f"   (in {cwd})" if cwd else ""))
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, **(env or {})}, timeout=timeout, creationflags=NO_WINDOW)
    if check and p.returncode != 0:
        msg = (p.stderr or p.stdout).strip()
        _log(f"  ! exit {p.returncode}: {msg[:400]}")
        raise GitError(msg or f"{args[0]} exited {p.returncode}")
    return p


def git(*args, cwd=None, check=True, env=None) -> str:
    return run(["git", *args], cwd=cwd, check=check, env=env).stdout.strip()


def fwd(p) -> str:
    return str(p).replace("\\", "/")


# ---------------------------------------------------------------- profiles
@dataclass
class Profile:
    id: str
    label: str
    name: str
    email: str
    github_user: str = ""
    ssh_key: str = ""          # private key path; empty = use ssh defaults
    color: str = "#2a6fdb"

    def validate(self) -> None:
        if not ID_RE.match(self.id):
            raise ValueError("Profile id: lowercase letters, digits, - or _ (max 32)")
        if not self.label.strip():
            raise ValueError("Label is required")
        if not SAFE_TEXT_RE.match(self.name):
            raise ValueError('Name is required and must not contain " ` $ \\ < >')
        if not EMAIL_RE.match(self.email):
            raise ValueError("Email looks invalid")
        if self.github_user and not re.match(r"^[A-Za-z0-9-]{1,39}$", self.github_user):
            raise ValueError("GitHub username looks invalid")
        if self.ssh_key and not Path(self.ssh_key).is_file():
            raise ValueError(f"SSH key not found: {self.ssh_key}")

    @property
    def ssh_command(self) -> str:
        return f"ssh -i '{fwd(self.ssh_key)}' -o IdentitiesOnly=yes" if self.ssh_key else ""

    @property
    def include_file(self) -> Path:
        return CONFIG_DIR / f"{self.id}.gitconfig"

    def display(self) -> str:
        gh = f" @{self.github_user}" if self.github_user else ""
        return f"{self.label}{gh} <{self.email}>"


@dataclass
class Rule:
    folder: str
    profile_id: str


@dataclass
class Store:
    profiles: list[Profile] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    recent_repos: list[str] = field(default_factory=list)

    def get(self, pid: str) -> Profile | None:
        return next((p for p in self.profiles if p.id == pid), None)

    def by_email(self, email: str) -> Profile | None:
        e = (email or "").lower()
        return next((p for p in self.profiles if p.email.lower() == e), None)

    def upsert(self, prof: Profile) -> None:
        prof.validate()
        for i, p in enumerate(self.profiles):
            if p.id == prof.id:
                self.profiles[i] = prof
                return
        self.profiles.append(prof)

    def remove(self, pid: str) -> None:
        if any(r.profile_id == pid for r in self.rules):
            raise ValueError("Profile is used by a folder rule; remove the rule first")
        self.profiles = [p for p in self.profiles if p.id != pid]

    def touch_repo(self, path: str) -> None:
        path = fwd(Path(path).resolve())
        self.recent_repos = [path] + [r for r in self.recent_repos if r != path][:14]

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = PROFILES_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"profiles": [asdict(p) for p in self.profiles],
                                   "rules": [asdict(r) for r in self.rules],
                                   "recent_repos": self.recent_repos}, indent=2), "utf-8")
        os.replace(tmp, PROFILES_FILE)
        for p in self.profiles:
            write_include(p)


def load() -> Store:
    if not PROFILES_FILE.exists():
        s = Store()
        seed = detect_global_profile()
        if seed:
            s.profiles.append(seed)
        return s
    d = json.loads(PROFILES_FILE.read_text("utf-8"))
    return Store([Profile(**p) for p in d.get("profiles", [])], [Rule(**r) for r in d.get("rules", [])],
                 d.get("recent_repos", []))


def detect_global_profile() -> Profile | None:
    name = git("config", "--global", "user.name", check=False)
    email = git("config", "--global", "user.email", check=False)
    if not name or not email:
        return None
    return Profile(id="work", label="Work", name=name, email=email,
                   github_user=name if re.match(r"^[A-Za-z0-9-]{1,39}$", name) else "", color="#b7791f")


def write_include(p: Profile) -> Path:
    """Per-profile git config fragment, used by folder rules (includeIf)."""
    lines = ["# managed by gitaccounts - edit the profile in the app instead", "[user]",
             f"\tname = {p.name}", f"\temail = {p.email}", "[gitaccounts]", f"\tprofile = {p.id}"]
    if p.ssh_key:
        lines += ["[core]", f'\tsshCommand = "{p.ssh_command}"']
    if p.github_user:
        lines += ["[credential]", f"\tusername = {p.github_user}"]
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    p.include_file.write_text("\n".join(lines) + "\n", "utf-8")
    return p.include_file


# ---------------------------------------------------------------- repo status
def repo_root(path: str) -> str | None:
    r = run(["git", "rev-parse", "--show-toplevel"], cwd=path, check=False)
    return r.stdout.strip() if r.returncode == 0 else None


def _get_with_origin(key: str, cwd: str) -> tuple[str, str]:
    r = run(["git", "config", "--show-origin", "--show-scope", "--get", key], cwd=cwd, check=False)
    if r.returncode != 0 or not r.stdout.strip():
        return "", ""
    scope, origin, value = (r.stdout.rstrip("\n").split("\t", 2) + ["", ""])[:3]
    return value, f"{scope} ({origin.replace('file:', '')})"


def status(path: str, store: Store) -> dict:
    root = repo_root(path)
    st = {"path": fwd(path), "is_repo": bool(root), "root": root}
    cwd = root or path
    name, name_src = _get_with_origin("user.name", cwd)
    email, email_src = _get_with_origin("user.email", cwd)
    ssh_cmd, ssh_src = _get_with_origin("core.sshCommand", cwd)
    st.update(name=name, email=email, identity_source=email_src or name_src, ssh_command=ssh_cmd, ssh_source=ssh_src)
    prof = store.by_email(email)
    st["profile"] = prof.id if prof else None
    st["rule"] = matching_rule(cwd, store)
    if not root:
        return st
    st["branch"] = git("branch", "--show-current", cwd=root, check=False) or "(detached)"
    st["remotes"] = {}
    for line in git("remote", "-v", cwd=root, check=False).splitlines():
        parts = line.split()
        if len(parts) >= 2:
            st["remotes"][parts[0]] = parts[1]
    st["changes"] = [l for l in git("status", "--porcelain", cwd=root, check=False).splitlines() if l.strip()]
    has_head = run(["git", "rev-parse", "--verify", "HEAD"], cwd=root, check=False).returncode == 0
    st["has_commits"] = has_head
    st["upstream"] = git("rev-parse", "--abbrev-ref", "@{u}", cwd=root, check=False) if has_head else ""
    st["unpushed"] = unpushed_commits(root) if has_head else []
    st["authors"] = sorted(set(git("log", "--format=%an <%ae>", cwd=root, check=False).splitlines())) if has_head else []
    return st


def matching_rule(path: str, store: Store) -> Rule | None:
    p = fwd(Path(path).resolve()).lower().rstrip("/") + "/"
    best = None
    for r in store.rules:
        f = fwd(r.folder).lower().rstrip("/") + "/"
        if p.startswith(f) and (best is None or len(f) > len(fwd(best.folder))):
            best = r
    return best


def unpushed_commits(root: str) -> list[dict]:
    """Commits on HEAD that are not on any remote-tracking branch."""
    out = git("log", "--format=%H%x09%h%x09%an <%ae>%x09%s", "HEAD", "--not", "--remotes", cwd=root, check=False)
    res = []
    for line in out.splitlines():
        full, short, author, subject = (line.split("\t", 3) + ["", "", ""])[:4]
        res.append({"sha": full, "short": short, "author": author, "subject": subject})
    return res


# ---------------------------------------------------------------- actions
def use_profile(path: str, prof: Profile) -> None:
    """Pin a repo to a profile (repo-local config, overrides global and folder rules)."""
    root = repo_root(path)
    if not root:
        raise GitError("Not a git repository")
    git("config", "--local", "user.name", prof.name, cwd=root)
    git("config", "--local", "user.email", prof.email, cwd=root)
    git("config", "--local", "gitaccounts.profile", prof.id, cwd=root)
    if prof.ssh_key:
        git("config", "--local", "core.sshCommand", prof.ssh_command, cwd=root)
    else:
        git("config", "--local", "--unset-all", "core.sshCommand", cwd=root, check=False)
    if prof.github_user:
        git("config", "--local", "credential.username", prof.github_user, cwd=root)
    else:
        git("config", "--local", "--unset-all", "credential.username", cwd=root, check=False)


def clear_repo_profile(path: str) -> None:
    root = repo_root(path)
    if not root:
        raise GitError("Not a git repository")
    for k in MANAGED_KEYS:
        git("config", "--local", "--unset-all", k, cwd=root, check=False)


def init_repo(path: str, prof: Profile, branch: str = "main") -> None:
    Path(path).mkdir(parents=True, exist_ok=True)
    git("init", "-b", branch, cwd=path)
    use_profile(path, prof)


def commit_all(path: str, message: str, expect: Profile) -> str:
    root = repo_root(path)
    if not root:
        raise GitError("Not a git repository")
    if not message.strip():
        raise GitError("Commit message is empty")
    email = git("config", "user.email", cwd=root, check=False)
    if email.lower() != expect.email.lower():
        raise GitError(f"This repo would commit as <{email}>, not the selected profile <{expect.email}>. "
                       "Click 'Use this profile here' first.")
    git("add", "-A", cwd=root)
    git("commit", "-m", message, cwd=root)
    return git("log", "-1", "--format=%h %an <%ae> %s", cwd=root)


def set_remote(path: str, url: str, name: str = "origin") -> None:
    root = repo_root(path)
    if not re.match(r"^(git@[\w.-]+:[\w./-]+|https://[\w.-]+/[\w./-]+|ssh://[\w@.:/-]+)$", url):
        raise GitError("Remote URL should look like git@github.com:user/repo.git or https://github.com/user/repo.git")
    if name in git("remote", cwd=root).split():
        git("remote", "set-url", name, url, cwd=root)
    else:
        git("remote", "add", name, url, cwd=root)


def push(path: str, expect: Profile, remote: str = "origin") -> str:
    root = repo_root(path)
    email = git("config", "user.email", cwd=root, check=False)
    if email.lower() != expect.email.lower():
        raise GitError(f"Repo is configured for <{email}>, not {expect.label}. Switch first.")
    branch = git("branch", "--show-current", cwd=root)
    r = run(["git", "push", "-u", remote, branch], cwd=root, check=True, env={"GIT_TERMINAL_PROMPT": "0"})
    return (r.stderr or r.stdout).strip()


def reauthor_unpushed(path: str, prof: Profile) -> int:
    """Rewrite author+committer of commits not on any remote to `prof`. Keeps author dates.
    A backup ref is written first: refs/gitaccounts/backup/<timestamp>."""
    root = repo_root(path)
    if not root:
        raise GitError("Not a git repository")
    if git("status", "--porcelain", "--untracked-files=no", cwd=root):
        raise GitError("Commit or stash your changes first (working tree has modifications)")
    commits = unpushed_commits(root)
    if not commits:
        return 0
    oldest = commits[-1]["sha"]
    parent = run(["git", "rev-parse", "--verify", f"{oldest}^"], cwd=root, check=False)
    base = ["--root"] if parent.returncode != 0 else [parent.stdout.strip()]
    git("update-ref", f"refs/gitaccounts/backup/{time.strftime('%Y%m%d-%H%M%S')}", "HEAD", cwd=root)
    author = f"{prof.name} <{prof.email}>"
    exec_cmd = f'git commit --amend --no-edit --allow-empty --author="{author}"'
    run(["git", "-c", f"user.name={prof.name}", "-c", f"user.email={prof.email}",
         "rebase", "--rebase-merges", "--committer-date-is-author-date", "--exec", exec_cmd, *base],
        cwd=root, env={"GIT_SEQUENCE_EDITOR": "true", "GIT_EDITOR": "true"})
    return len(commits)


# ---------------------------------------------------------------- folder rules -> global gitconfig
def apply_rules(store: Store) -> list[str]:
    """Rewrite the managed includeIf entries in the global git config from store.rules."""
    existing = git("config", "--global", "--get-regexp", r"^includeif\..*\.path$", check=False)
    mine = fwd(CONFIG_DIR).lower()
    for line in existing.splitlines():
        key, _, val = line.partition(" ")
        if fwd(val).lower().startswith(mine):
            git("config", "--global", "--unset-all", key, check=False)
    applied = []
    for r in store.rules:
        prof = store.get(r.profile_id)
        if not prof:
            continue
        write_include(prof)
        folder = fwd(Path(r.folder).resolve()).rstrip("/") + "/"
        git("config", "--global", "--add", f"includeIf.gitdir/i:{folder}.path", fwd(prof.include_file))
        applied.append(f"{folder} -> {prof.label}")
    return applied


def set_global_default(prof: Profile) -> None:
    git("config", "--global", "user.name", prof.name)
    git("config", "--global", "user.email", prof.email)


def global_identity() -> tuple[str, str]:
    return git("config", "--global", "user.name", check=False), git("config", "--global", "user.email", check=False)


# ---------------------------------------------------------------- ssh
def generate_key(prof: Profile) -> Path:
    SSH_DIR.mkdir(exist_ok=True)
    key = SSH_DIR / f"id_ed25519_{prof.id}"
    if key.exists():
        raise GitError(f"{key} already exists; pick it with 'Browse' instead")
    run(["ssh-keygen", "-t", "ed25519", "-f", str(key), "-N", "", "-C", prof.email, "-q"])
    return key


def public_key(prof: Profile) -> str:
    pub = Path(prof.ssh_key + ".pub")
    return pub.read_text("utf-8").strip() if pub.is_file() else ""


def test_ssh(prof: Profile) -> tuple[str | None, str]:
    """Return (github_user_that_key_authenticates_as or None, raw message)."""
    args = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10"]
    if prof.ssh_key:
        args += ["-i", prof.ssh_key, "-o", "IdentitiesOnly=yes"]
    r = run(args + ["git@github.com"], check=False, timeout=30)
    out = (r.stderr + r.stdout).strip()
    m = re.search(r"Hi ([A-Za-z0-9-]+)!", out)
    return (m.group(1) if m else None), out
