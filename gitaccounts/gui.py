"""Tkinter GUI for gitaccounts. Standard library only."""
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

from . import core

PAD = 8


class App(tk.Tk):
    def __init__(self, start_repo: str | None = None):
        super().__init__()
        self.title("Git Accounts")
        ico = Path(__file__).resolve().parents[1] / "assets" / "gitaccounts.ico"
        if ico.is_file():
            try:
                self.iconbitmap(default=str(ico))  # window + taskbar icon instead of the Tk feather
            except tk.TclError:
                pass
        self.geometry("1180x860")
        self.minsize(900, 680)
        self.store = core.load()
        if not core.PROFILES_FILE.exists():
            self.store.save()
        self.repo = tk.StringVar(value=start_repo or (self.store.recent_repos[0] if self.store.recent_repos else ""))
        self.sel_profile = tk.StringVar()
        self.status_data: dict = {}
        self._style()
        self._build()
        core.on_log(lambda line: self.after(0, self._append_log, line))
        self.refresh_profiles()
        self.refresh_repo()

    # ------------------------------------------------------------ layout
    def _style(self):
        s = ttk.Style(self)
        try:
            s.theme_use("vista")
        except tk.TclError:
            s.theme_use("clam")
        s.configure("Badge.TLabel", font=("Segoe UI", 15, "bold"), foreground="white", padding=(14, 8))
        s.configure("Sub.TLabel", foreground="#555")
        s.configure("H.TLabel", font=("Segoe UI", 10, "bold"))

    def _build(self):
        top = ttk.Frame(self, padding=PAD)
        top.pack(fill="x")
        self.badge = tk.Label(top, text="No repository selected", font=("Segoe UI", 15, "bold"), fg="white",
                              bg="#6b6f78", padx=14, pady=8, anchor="w")
        self.badge.pack(fill="x")
        self.badge_sub = ttk.Label(top, text="", style="Sub.TLabel")
        self.badge_sub.pack(fill="x", pady=(4, 0))

        # pack the log first at the bottom so it always keeps its space
        logf = ttk.LabelFrame(self, text="Commands run (nothing is hidden)", padding=4)
        logf.pack(side="bottom", fill="x", padx=PAD, pady=PAD)
        self.log = tk.Text(logf, height=5, font=("Consolas", 9), state="disabled", wrap="none")
        self.log.pack(fill="x")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=PAD)
        self.tab_repo = ttk.Frame(nb, padding=PAD)
        self.tab_prof = ttk.Frame(nb, padding=PAD)
        self.tab_rules = ttk.Frame(nb, padding=PAD)
        nb.add(self.tab_repo, text="  Repository  ")
        nb.add(self.tab_prof, text="  Accounts  ")
        nb.add(self.tab_rules, text="  Folder rules & default  ")
        self._build_repo()
        self._build_profiles()
        self._build_rules()

    def _build_repo(self):
        f = self.tab_repo
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Label(row, text="Repository folder:").pack(side="left")
        self.repo_box = ttk.Combobox(row, textvariable=self.repo, values=self.store.recent_repos)
        self.repo_box.pack(side="left", fill="x", expand=True, padx=6)
        self.repo_box.bind("<<ComboboxSelected>>", lambda e: self.refresh_repo())
        self.repo_box.bind("<Return>", lambda e: self.refresh_repo())
        ttk.Button(row, text="Browse…", command=self.browse_repo).pack(side="left")
        ttk.Button(row, text="Refresh", command=self.refresh_repo).pack(side="left", padx=(6, 0))

        body = ttk.Frame(f)
        body.pack(fill="both", expand=True, pady=(PAD, 0))
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(body, width=330)
        right.pack(side="left", fill="y", padx=(PAD, 0))

        self.info = tk.Text(left, height=14, font=("Consolas", 10), wrap="none", state="disabled", relief="flat",
                            background="#f6f5f2")
        self.info.pack(fill="both", expand=True)

        acc = ttk.LabelFrame(right, text="Account for this repository", padding=PAD)
        acc.pack(fill="x")
        self.prof_box = ttk.Combobox(acc, textvariable=self.sel_profile, state="readonly")
        self.prof_box.pack(fill="x")
        ttk.Button(acc, text="Use this account here", command=self.apply_profile).pack(fill="x", pady=(6, 0))
        ttk.Button(acc, text="Remove repo override", command=self.clear_profile).pack(fill="x", pady=(4, 0))

        act = ttk.LabelFrame(right, text="Actions (run as the account above)", padding=PAD)
        act.pack(fill="x", pady=(PAD, 0))
        ttk.Button(act, text="Initialize new repo here", command=self.init_repo).pack(fill="x")
        ttk.Label(act, text="Commit message:").pack(anchor="w", pady=(6, 0))
        self.msg = tk.Text(act, height=3, font=("Segoe UI", 9))
        self.msg.pack(fill="x")
        ttk.Button(act, text="Stage all + Commit", command=self.commit).pack(fill="x", pady=(4, 0))
        ttk.Button(act, text="Set remote URL…", command=self.set_remote).pack(fill="x", pady=(4, 0))
        ttk.Button(act, text="Push", command=self.push).pack(fill="x", pady=(4, 0))
        ttk.Button(act, text="Re-author unpushed commits…", command=self.reauthor).pack(fill="x", pady=(4, 0))
        ttk.Button(act, text="Test SSH login for account", command=self.test_selected_ssh).pack(fill="x", pady=(4, 0))

    def _build_profiles(self):
        f = self.tab_prof
        cols = ("label", "github", "email", "key")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=8, selectmode="browse")
        for c, w, t in zip(cols, (140, 140, 260, 340), ("Account", "GitHub user", "Commit email", "SSH key")):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.load_form())

        form = ttk.LabelFrame(f, text="Account details", padding=PAD)
        form.pack(fill="x", pady=(PAD, 0))
        self.fv = {k: tk.StringVar() for k in ("id", "label", "name", "email", "github_user", "ssh_key", "color")}
        rows = [("id", "Short id (e.g. personal, work)"), ("label", "Display name"),
                ("name", "Git author name"), ("email", "Commit email"), ("github_user", "GitHub username"),
                ("ssh_key", "SSH private key")]
        for i, (k, t) in enumerate(rows):
            ttk.Label(form, text=t).grid(row=i, column=0, sticky="w", pady=2)
            ttk.Entry(form, textvariable=self.fv[k], width=60).grid(row=i, column=1, sticky="we", pady=2, padx=6)
        form.columnconfigure(1, weight=1)
        ttk.Button(form, text="Browse…", command=self.pick_key).grid(row=5, column=2)
        ttk.Label(form, text="Badge colour").grid(row=6, column=0, sticky="w")
        self.color_btn = tk.Button(form, text="  pick  ", command=self.pick_color, relief="groove")
        self.color_btn.grid(row=6, column=1, sticky="w", padx=6)
        ttk.Label(form, text="Tip: use GitHub's private noreply email (Settings → Emails) to keep your address private.",
                  style="Sub.TLabel").grid(row=7, column=0, columnspan=3, sticky="w", pady=(6, 0))

        btns = ttk.Frame(f)
        btns.pack(fill="x", pady=PAD)
        for t, cmd in (("New", self.new_profile), ("Save", self.save_profile), ("Delete", self.delete_profile),
                       ("Generate SSH key", self.gen_key), ("Copy public key", self.copy_pub),
                       ("Open GitHub SSH settings", lambda: webbrowser.open("https://github.com/settings/ssh/new")),
                       ("Test SSH login", self.test_form_ssh)):
            ttk.Button(btns, text=t, command=cmd).pack(side="left", padx=(0, 6))

    def _build_rules(self):
        f = self.tab_rules
        ttk.Label(f, text="Folder rules: every repo inside a folder automatically uses an account "
                         "(applied to your global git config with includeIf). A repo override still wins.",
                  wraplength=900).pack(anchor="w")
        self.rules = ttk.Treeview(f, columns=("folder", "account"), show="headings", height=7)
        self.rules.heading("folder", text="Folder")
        self.rules.heading("account", text="Account")
        self.rules.column("folder", width=560)
        self.rules.pack(fill="x", pady=PAD)
        r = ttk.Frame(f)
        r.pack(fill="x")
        self.rule_prof = ttk.Combobox(r, state="readonly", width=30)
        self.rule_prof.pack(side="left")
        ttk.Button(r, text="Add folder rule…", command=self.add_rule).pack(side="left", padx=6)
        ttk.Button(r, text="Remove selected", command=self.remove_rule).pack(side="left")
        ttk.Button(r, text="Apply rules to git", command=self.apply_rules).pack(side="left", padx=6)

        g = ttk.LabelFrame(f, text="Global default (repos with no rule and no override)", padding=PAD)
        g.pack(fill="x", pady=(PAD * 2, 0))
        self.global_lbl = ttk.Label(g, text="")
        self.global_lbl.pack(anchor="w")
        gr = ttk.Frame(g)
        gr.pack(fill="x", pady=(6, 0))
        self.global_prof = ttk.Combobox(gr, state="readonly", width=30)
        self.global_prof.pack(side="left")
        ttk.Button(gr, text="Make default", command=self.set_global).pack(side="left", padx=6)

    # ------------------------------------------------------------ helpers
    def _append_log(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _bg(self, fn, done=None, busy="Working…"):
        self.config(cursor="watch")
        self.badge_sub.configure(text=busy)

        def work():
            try:
                res = fn()
                self.after(0, lambda: (self.config(cursor=""), done and done(res), self.refresh_repo()))
            except Exception as e:
                self.after(0, lambda e=e: (self.config(cursor=""), messagebox.showerror("Git Accounts", str(e)),
                                           self.refresh_repo()))
        threading.Thread(target=work, daemon=True).start()

    def _profile_names(self):
        return [p.display() for p in self.store.profiles]

    def _selected(self) -> core.Profile | None:
        i = self.prof_box.current()
        return self.store.profiles[i] if i >= 0 else None

    def _require(self):
        p = self._selected()
        if not p:
            messagebox.showwarning("Git Accounts", "Pick an account first.")
        return p

    # ------------------------------------------------------------ repo tab
    def browse_repo(self):
        d = filedialog.askdirectory(initialdir=self.repo.get() or str(Path.home()))
        if d:
            self.repo.set(d)
            self.refresh_repo()

    def refresh_repo(self):
        path = self.repo.get().strip()
        self._update_global_label()
        if not path or not Path(path).is_dir():
            self._set_badge(None, "No repository selected", "Choose a folder above.")
            self._set_info("")
            return
        try:
            st = core.status(path, self.store)
        except Exception as e:
            self._set_info(f"Error: {e}")
            return
        self.status_data = st
        if st["is_repo"]:
            self.store.touch_repo(st["root"])
            self.store.save()
            self.repo_box.configure(values=self.store.recent_repos)
        prof = self.store.get(st["profile"]) if st["profile"] else None
        if prof:
            self.prof_box.current(self.store.profiles.index(prof))
        ident = f"{st['name']} <{st['email']}>" if st["email"] else "no identity configured"
        if not st["is_repo"]:
            self._set_badge(prof, "Not a git repository yet", f"Would use: {ident}")
        elif prof:
            self._set_badge(prof, f"Using: {prof.label}" + (f"  (@{prof.github_user})" if prof.github_user else ""),
                            f"{ident} — from {st['identity_source']}")
        else:
            self._set_badge(None, f"Unknown account: {ident}", f"from {st['identity_source'] or 'nowhere'} — "
                                                               "pick an account and click 'Use this account here'")
        lines = [f"Folder        {st['root'] or st['path']}"]
        lines += [f"Identity      {ident}", f"  set by      {st['identity_source'] or '-'}"]
        lines += [f"Push key      {st['ssh_command'] or 'ssh defaults (~/.ssh/config)'}"]
        if st["rule"]:
            rp = self.store.get(st["rule"].profile_id)
            lines += [f"Folder rule   {st['rule'].folder} -> {rp.label if rp else st['rule'].profile_id}"]
        if st["is_repo"]:
            lines += [f"Branch        {st['branch']}   upstream: {st['upstream'] or 'none'}"]
            for n, u in st["remotes"].items():
                lines += [f"Remote        {n}  {u}"]
            if not st["remotes"]:
                lines += ["Remote        none"]
            lines += [f"Changes       {len(st['changes'])} file(s) changed"]
            lines += [f"Unpushed      {len(st['unpushed'])} commit(s)"]
            for c in st["unpushed"][:8]:
                lines += [f"   {c['short']}  {c['author']}", f"            {c['subject'][:58]}"]
            if len(st["authors"]) > 0:
                lines += ["Authors in history:"] + [f"   {a}" for a in st["authors"][:6]]
            wrong = [c for c in st["unpushed"] if prof and prof.email.lower() not in c["author"].lower()]
            if wrong:
                lines += ["", f"⚠ {len(wrong)} unpushed commit(s) are not by {prof.label}. "
                              "Use 'Re-author unpushed commits…' before pushing."]
        self._set_info("\n".join(lines))

    def _set_badge(self, prof, text, sub):
        self.badge.configure(text=text, bg=prof.color if prof else "#6b6f78")
        self.badge_sub.configure(text=sub)

    def _set_info(self, text):
        self.info.configure(state="normal")
        self.info.delete("1.0", "end")
        self.info.insert("1.0", text)
        self.info.configure(state="disabled")

    def apply_profile(self):
        p = self._require()
        if p:
            self._bg(lambda: core.use_profile(self.repo.get(), p))

    def clear_profile(self):
        if messagebox.askyesno("Git Accounts", "Remove this repo's account override? It will fall back to "
                                               "folder rules or the global default."):
            self._bg(lambda: core.clear_repo_profile(self.repo.get()))

    def init_repo(self):
        p = self._require()
        if not p:
            return
        if self.status_data.get("is_repo"):
            messagebox.showinfo("Git Accounts", "This folder is already a git repository.")
            return
        if messagebox.askyesno("Git Accounts", f"Run 'git init' in\n{self.repo.get()}\nand pin it to {p.label}?"):
            self._bg(lambda: core.init_repo(self.repo.get(), p))

    def commit(self):
        p = self._require()
        msg = self.msg.get("1.0", "end").strip()
        if not p:
            return
        n = len(self.status_data.get("changes", []))
        if messagebox.askyesno("Git Accounts", f"Stage all {n} changed file(s) and commit as\n"
                                               f"{p.name} <{p.email}>?"):
            self._bg(lambda: core.commit_all(self.repo.get(), msg, p),
                     lambda r: (self.msg.delete("1.0", "end"), messagebox.showinfo("Committed", r)))

    def set_remote(self):
        p = self._selected()
        hint = f"git@github.com:{p.github_user}/REPO.git" if p and p.github_user else "git@github.com:USER/REPO.git"
        url = simple_input(self, "Remote URL", f"origin URL (e.g. {hint})",
                           self.status_data.get("remotes", {}).get("origin", ""))
        if url:
            self._bg(lambda: core.set_remote(self.repo.get(), url))

    def push(self):
        p = self._require()
        if not p:
            return
        remote = self.status_data.get("remotes", {}).get("origin")
        if not remote:
            messagebox.showwarning("Git Accounts", "No 'origin' remote. Use 'Set remote URL…' first.")
            return
        if messagebox.askyesno("Git Accounts", f"Push branch '{self.status_data.get('branch')}' to\n{remote}\n"
                                               f"using {p.label}'s key?"):
            self._bg(lambda: core.push(self.repo.get(), p), lambda r: messagebox.showinfo("Pushed", r or "Done"),
                     busy="Pushing…")

    def reauthor(self):
        p = self._require()
        if not p:
            return
        n = len(self.status_data.get("unpushed", []))
        if not n:
            messagebox.showinfo("Git Accounts", "No unpushed commits.")
            return
        if messagebox.askyesno("Git Accounts", f"Rewrite the author of {n} unpushed commit(s) to\n"
                                               f"{p.name} <{p.email}>?\n\nCommits already on a remote are not "
                                               "touched. A backup ref is saved first."):
            self._bg(lambda: core.reauthor_unpushed(self.repo.get(), p),
                     lambda k: messagebox.showinfo("Done", f"Rewrote {k} commit(s)."))

    def test_selected_ssh(self):
        p = self._require()
        if p:
            self._run_ssh_test(p)

    def _run_ssh_test(self, p):
        def done(res):
            user, raw = res
            if not user:
                messagebox.showerror("SSH test", f"{p.label}: login failed.\n\n{raw[:500]}")
            elif p.github_user and user.lower() != p.github_user.lower():
                messagebox.showwarning("SSH test", f"{p.label}'s key logs in as @{user}, "
                                                   f"not @{p.github_user}. Pushes would go to the wrong account.")
            else:
                messagebox.showinfo("SSH test", f"{p.label}'s key logs in to GitHub as @{user}. ✓")
        self._bg(lambda: core.test_ssh(p), done, busy=f"Testing SSH for {p.label}…")

    # ------------------------------------------------------------ accounts tab
    def refresh_profiles(self):
        self.tree.delete(*self.tree.get_children())
        for p in self.store.profiles:
            self.tree.insert("", "end", iid=p.id, values=(p.label, p.github_user, p.email, p.ssh_key or "(ssh defaults)"))
        names = self._profile_names()
        for box in (self.prof_box, self.rule_prof, self.global_prof):
            box.configure(values=names)
        self.rules.delete(*self.rules.get_children())
        for i, r in enumerate(self.store.rules):
            p = self.store.get(r.profile_id)
            self.rules.insert("", "end", iid=str(i), values=(r.folder, p.label if p else r.profile_id))

    def load_form(self):
        sel = self.tree.selection()
        p = self.store.get(sel[0]) if sel else None
        if p:
            for k, v in self.fv.items():
                v.set(getattr(p, k))
            self.color_btn.configure(bg=p.color)

    def new_profile(self):
        for v in self.fv.values():
            v.set("")
        self.fv["color"].set("#2a6fdb")
        self.color_btn.configure(bg="#2a6fdb")
        self.tree.selection_remove(self.tree.selection())

    def _form_profile(self):
        d = {k: v.get().strip() for k, v in self.fv.items()}
        d["color"] = d["color"] or "#2a6fdb"
        return core.Profile(**d)

    def save_profile(self):
        try:
            p = self._form_profile()
            self.store.upsert(p)
            self.store.save()
        except ValueError as e:
            messagebox.showerror("Account", str(e))
            return
        self.refresh_profiles()
        self.tree.selection_set(p.id)
        self.refresh_repo()

    def delete_profile(self):
        sel = self.tree.selection()
        if sel and messagebox.askyesno("Account", f"Delete account '{sel[0]}' from this app?\n"
                                                  "(Keys and repos are not touched.)"):
            try:
                self.store.remove(sel[0])
                self.store.save()
            except ValueError as e:
                messagebox.showerror("Account", str(e))
            self.refresh_profiles()

    def pick_key(self):
        f = filedialog.askopenfilename(initialdir=str(core.SSH_DIR), title="Private key (not .pub)")
        if f:
            self.fv["ssh_key"].set(f[:-4] if f.endswith(".pub") else f)

    def pick_color(self):
        c = colorchooser.askcolor(self.fv["color"].get() or "#2a6fdb")[1]
        if c:
            self.fv["color"].set(c)
            self.color_btn.configure(bg=c)

    def gen_key(self):
        try:
            p = self._form_profile()
            p.ssh_key = ""
            p.validate()
            key = core.generate_key(p)
        except Exception as e:
            messagebox.showerror("SSH key", str(e))
            return
        self.fv["ssh_key"].set(str(key))
        self.save_profile()
        self.copy_pub()
        messagebox.showinfo("SSH key", f"Created {key}\n\nThe public key is on your clipboard. Add it on GitHub "
                                       "(signed in as THIS account), then click 'Test SSH login'.")
        webbrowser.open("https://github.com/settings/ssh/new")

    def copy_pub(self):
        try:
            pub = core.public_key(self._form_profile())
        except Exception:
            pub = ""
        if not pub:
            messagebox.showwarning("SSH key", "No .pub file next to this key.")
            return
        self.clipboard_clear()
        self.clipboard_append(pub)

    def test_form_ssh(self):
        try:
            self._run_ssh_test(self._form_profile())
        except Exception as e:
            messagebox.showerror("SSH test", str(e))

    # ------------------------------------------------------------ rules tab
    def add_rule(self):
        i = self.rule_prof.current()
        if i < 0:
            messagebox.showwarning("Rules", "Pick an account first.")
            return
        d = filedialog.askdirectory(title="Folder whose repos should use this account")
        if d:
            self.store.rules.append(core.Rule(core.fwd(d), self.store.profiles[i].id))
            self.store.save()
            self.refresh_profiles()

    def remove_rule(self):
        for iid in sorted(self.rules.selection(), key=int, reverse=True):
            del self.store.rules[int(iid)]
        self.store.save()
        self.refresh_profiles()

    def apply_rules(self):
        preview = "\n".join(f"{r.folder}  ->  {self.store.get(r.profile_id).label}" for r in self.store.rules) or "(none)"
        if messagebox.askyesno("Rules", f"Write these rules into your global git config (~/.gitconfig)?\n\n{preview}"):
            self._bg(lambda: core.apply_rules(self.store),
                     lambda res: messagebox.showinfo("Rules", "Applied:\n" + ("\n".join(res) or "(no rules)")))

    def set_global(self):
        i = self.global_prof.current()
        if i < 0:
            return
        p = self.store.profiles[i]
        if messagebox.askyesno("Default", f"Make {p.label} <{p.email}> the global default identity?"):
            self._bg(lambda: core.set_global_default(p))

    def _update_global_label(self):
        n, e = core.global_identity()
        p = self.store.by_email(e)
        self.global_lbl.configure(text=f"Current global default: {n} <{e}>" + (f"  ({p.label})" if p else ""))


def simple_input(parent, title, prompt, initial=""):
    win = tk.Toplevel(parent)
    win.title(title)
    win.transient(parent)
    win.grab_set()
    ttk.Label(win, text=prompt).pack(padx=PAD, pady=(PAD, 4), anchor="w")
    v = tk.StringVar(value=initial)
    e = ttk.Entry(win, textvariable=v, width=70)
    e.pack(padx=PAD)
    e.focus_set()
    out = {"v": None}

    def ok(*_):
        out["v"] = v.get().strip()
        win.destroy()
    b = ttk.Frame(win)
    b.pack(pady=PAD)
    ttk.Button(b, text="OK", command=ok).pack(side="left", padx=4)
    ttk.Button(b, text="Cancel", command=win.destroy).pack(side="left")
    win.bind("<Return>", ok)
    parent.wait_window(win)
    return out["v"]


def _dpi_aware():
    try:  # crisp text on scaled Windows displays
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        # own taskbar group (and icon) instead of the generic pythonw one
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("local.gitaccounts")
    except Exception:
        pass


def main(start_repo=None):
    _dpi_aware()
    App(start_repo).mainloop()
