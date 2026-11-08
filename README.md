# Git Accounts

A small Windows app (GUI and CLI) that keeps your **work** and **personal** Git/GitHub accounts apart.
It always shows which account a repository will commit and push as, and lets you switch with one click.
It uses only the Python standard library (3.10+), so there is nothing to install.

![icon](assets/gitaccounts.png)

## Why
With two GitHub accounts on one PC it is easy to:
- commit to a personal project under your work email, because the global `user.email` wins, or
- push with the wrong SSH key, because `~/.ssh/config` picked the other one.

Git Accounts makes the active account visible and lets you fix it per repository or per folder.

## Install
1. Install [Python 3.10+](https://www.python.org/downloads/windows/) with tcl/tk (the default), and [Git for Windows](https://git-scm.com/).
2. Download or clone this repository.
3. Double-click `install-shortcuts.cmd`. This adds **Git Accounts** to the Start menu and the Desktop.
   Or double-click `GitAccounts.pyw` directly.

## Features
- **Badge** showing the account the selected repo uses, in that account's colour, and where it comes from:
  repo, folder rule or global default.
- **Repository tab**
  - Pin a repo to an account.
  - `git init`, *Stage all + Commit*, *Set remote URL*, *Push*.
  - Commit and push refuse to run if the repo's identity doesn't match the selected account.
  - *Re-author unpushed commits* fixes commits made under the wrong account. It only touches commits that are not on any remote, keeps author dates, and saves a backup ref under `refs/gitaccounts/backup/`.
- **Accounts tab**
  - Name, commit email, GitHub username, SSH key.
  - *Generate SSH key* creates a key and copies the public part to the clipboard.
  - *Test SSH login* shows which GitHub user a key really logs in as, and warns on a mismatch.
- **Folder rules**: for example, "everything under `C:\dev\` uses Personal". The rule is written to your global git config as `includeIf`, so it also applies in the terminal, VS Code and other tools. Your own `includeIf` entries are left alone.
- **Command log**: every git and ssh command the app runs is listed. Nothing is hidden.

## How switching works
| Level | Stored in | Wins over |
|---|---|---|
| Repo pin | the repo's `.git/config`: `user.*`, `core.sshCommand`, `credential.username` | everything |
| Folder rule | `~/.gitconfig` `includeIf "gitdir/i:<folder>/"` → `~/.gitaccounts/<id>.gitconfig` | global default |
| Global default | `~/.gitconfig` `user.*` | – |

- **SSH pushes** use the account's key through `core.sshCommand ... -o IdentitiesOnly=yes`.
- **HTTPS pushes** go through Git Credential Manager, which picks the account from `credential.username`.

## CLI
```bat
gitacct list
gitacct status C:\path\to\repo
gitacct use personal C:\path\to\repo
gitacct test personal
gitacct reauthor personal C:\path\to\repo
```

## Data and privacy
`~/.gitaccounts/profiles.json` holds the accounts, rules and recent repos. The app stores **no passwords or tokens**
and makes no network calls, apart from `ssh -T git@github.com` when you click *Test SSH login* and the git commands you trigger.

## Tests
```bat
py -3 tests\test_core.py
```
The tests run against a temporary home folder and global git config; your real `~/.gitconfig` is never touched.

## Status
Early (0.1). It is tested on Windows 11 with Python 3.11 and 3.14 and Git 2.43. macOS and Linux are not supported yet.

## License
MIT
