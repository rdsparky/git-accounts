"""Command line for gitaccounts (for scripts and AI coding agents; the GUI uses the same core).

  python -m gitaccounts                         open the GUI
  python -m gitaccounts gui [REPO]              open the GUI on a repo
  python -m gitaccounts status [REPO]           which account a repo uses, and where that comes from
  python -m gitaccounts list                    accounts and folder rules
  python -m gitaccounts use ACCOUNT [REPO]      pin a repo to an account
  python -m gitaccounts clear [REPO]            remove the repo pin
  python -m gitaccounts test ACCOUNT            which GitHub user the account's SSH key logs in as
  python -m gitaccounts reauthor ACCOUNT [REPO] rewrite unpushed commits to ACCOUNT (backup ref kept)
"""
import argparse
import json
import sys

from . import core


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="gitaccounts", description="Switch Git/GitHub accounts per repository")
    sub = ap.add_subparsers(dest="cmd")
    g = sub.add_parser("gui")
    g.add_argument("repo", nargs="?")
    s = sub.add_parser("status")
    s.add_argument("repo", nargs="?", default=".")
    s.add_argument("--json", action="store_true")
    sub.add_parser("list")
    u = sub.add_parser("use")
    u.add_argument("account")
    u.add_argument("repo", nargs="?", default=".")
    c = sub.add_parser("clear")
    c.add_argument("repo", nargs="?", default=".")
    t = sub.add_parser("test")
    t.add_argument("account")
    r = sub.add_parser("reauthor")
    r.add_argument("account")
    r.add_argument("repo", nargs="?", default=".")
    args = ap.parse_args(argv)

    if args.cmd in (None, "gui"):
        from .gui import main as gui_main
        gui_main(getattr(args, "repo", None))
        return 0

    store = core.load()

    def need(pid):
        p = store.get(pid)
        if not p:
            raise SystemExit(f"unknown account '{pid}'. Known: {', '.join(x.id for x in store.profiles) or 'none'}")
        return p

    if args.cmd == "list":
        for p in store.profiles:
            print(f"{p.id:12} {p.display():60} key={p.ssh_key or '(ssh defaults)'}")
        for rule in store.rules:
            print(f"rule  {rule.folder}  ->  {rule.profile_id}")
        n, e = core.global_identity()
        print(f"global default: {n} <{e}>")
    elif args.cmd == "status":
        st = core.status(args.repo, store)
        if args.json:
            st["rule"] = st["rule"].__dict__ if st["rule"] else None
            print(json.dumps(st, indent=1))
        else:
            p = store.get(st["profile"]) if st["profile"] else None
            print(f"account : {p.label if p else 'UNKNOWN'}  ->  {st['name']} <{st['email']}>")
            print(f"set by  : {st['identity_source'] or '-'}")
            print(f"push key: {st['ssh_command'] or 'ssh defaults'}")
            if st.get("is_repo"):
                print(f"remotes : {st['remotes'] or 'none'}")
                print(f"unpushed: {len(st['unpushed'])} commit(s); authors: {', '.join(st['authors']) or '-'}")
    elif args.cmd == "use":
        p = need(args.account)
        core.use_profile(args.repo, p)
        print(f"{core.repo_root(args.repo)} now uses {p.display()}")
    elif args.cmd == "clear":
        core.clear_repo_profile(args.repo)
        print("repo override removed")
    elif args.cmd == "test":
        p = need(args.account)
        user, raw = core.test_ssh(p)
        print(f"{p.label}: key logs in as @{user}" if user else f"{p.label}: login failed: {raw}")
        if user and p.github_user and user.lower() != p.github_user.lower():
            print(f"WARNING: expected @{p.github_user}")
            return 2
        return 0 if user else 1
    elif args.cmd == "reauthor":
        p = need(args.account)
        n = core.reauthor_unpushed(args.repo, p)
        print(f"rewrote {n} unpushed commit(s) to {p.display()}")
    store.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
