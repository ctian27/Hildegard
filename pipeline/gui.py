"""Simple desktop GUI for the surveillance pipeline.

Pick disease groups with checkboxes, set a few options, and run the cycle
with one button. Output streams into the log pane. Built on Tkinter (ships
with Python -- no extra dependencies).

Launch:
    python -m pipeline.gui
"""

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from datetime import date
from tkinter import ttk, scrolledtext

from . import config

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_window_note() -> str:
    """Human-readable description of the default rolling window, derived from
    config so it stays accurate (e.g. '14 days back from today (CHIP: 30)')."""
    from collections import Counter

    active = config.ACTIVE_GROUPS
    if not active:
        return "each group's default window"
    common = Counter(g.window_days for g in active).most_common(1)[0][0]
    note = f"{common} days back from today"
    exceptions = [g for g in active if g.window_days != common]
    if exceptions:
        note += " (" + ", ".join(f"{g.key.upper()}: {g.window_days}" for g in exceptions) + ")"
    return note


def _validate_date(label: str, value: str) -> str:
    value = value.strip()
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{label} must be in YYYY-MM-DD format (got {value!r}).")
    return value


def build_command(groups: list[str], fmt: str, ignore_seen: bool, dry_run: bool,
                   max_items: str = "", start_date: str = "", end_date: str = "",
                   use_llm: bool = True) -> list[str]:
    """Assemble the `python -m pipeline.main ...` argv from GUI selections.
    Raises ValueError on invalid input (no groups, non-numeric max_items,
    or a malformed / reversed date range)."""
    if not groups:
        raise ValueError("Select at least one disease group.")
    cmd = [sys.executable, "-m", "pipeline.main"]
    for g in groups:
        cmd += ["--group", g]
    cmd += ["--format", fmt]
    if not use_llm:
        cmd.append("--no-llm")
    if ignore_seen:
        cmd.append("--ignore-seen")
    if dry_run:
        cmd.append("--dry-run")
    max_items = (max_items or "").strip()
    if max_items:
        if not max_items.isdigit():
            raise ValueError(f"Max items must be a whole number (got {max_items!r}).")
        cmd += ["--max-items", max_items]
    start_date = (start_date or "").strip()
    end_date = (end_date or "").strip()
    if start_date:
        start_date = _validate_date("Start date", start_date)
    if end_date:
        end_date = _validate_date("End date", end_date)
    if start_date and end_date and date.fromisoformat(start_date) > date.fromisoformat(end_date):
        raise ValueError("Start date is after end date.")
    if start_date:
        cmd += ["--start-date", start_date]
    if end_date:
        cmd += ["--end-date", end_date]
    return cmd


class PipelineGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Heme/Onc Literature Surveillance")
        self.proc: subprocess.Popen | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.group_vars: dict[str, tk.BooleanVar] = {}

        self._build_ui()
        self.root.after(100, self._drain_log)

    # --- UI construction --------------------------------------------------
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        # Disease groups, split into Hematologic / Solid tumor subsections.
        groups_frame = ttk.LabelFrame(self.root, text="Disease groups (active)")
        groups_frame.grid(row=0, column=0, sticky="nsew", **pad)
        active = config.ACTIVE_GROUPS
        heme = [g for g in active if g.category == "hematologic"]
        solid = [g for g in active if g.category == "solid_tumor"]

        heme_frame = self._build_group_section(groups_frame, "Hematologic", heme, cols=2)
        heme_frame.grid(row=0, column=0, sticky="nw", padx=(0, 10))
        solid_frame = self._build_group_section(groups_frame, "Solid tumor", solid, cols=2)
        solid_frame.grid(row=0, column=1, sticky="nw")

        btns = ttk.Frame(groups_frame)
        btns.grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=(6, 2))
        ttk.Button(btns, text="Select all", command=self._select_all).pack(side="left", padx=2)
        ttk.Button(btns, text="Clear", command=self._clear_all).pack(side="left", padx=2)

        # Options
        opts = ttk.LabelFrame(self.root, text="Options")
        opts.grid(row=1, column=0, sticky="nsew", **pad)

        self.format_var = tk.StringVar(value="both")
        ttk.Label(opts, text="Output format:").grid(row=0, column=0, sticky="w", padx=6)
        for i, (label, val) in enumerate([("PDF + Markdown", "both"), ("PDF only", "pdf"), ("Markdown only", "md")]):
            ttk.Radiobutton(opts, text=label, value=val, variable=self.format_var).grid(
                row=0, column=1 + i, sticky="w", padx=6)

        self.use_llm_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Use AI summaries (Claude) — uncheck for abstracts only (no API key needed)",
                        variable=self.use_llm_var).grid(row=1, column=0, columnspan=4, sticky="w", padx=6, pady=2)

        self.ignore_seen_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Ignore previously seen papers (regenerate full window)",
                        variable=self.ignore_seen_var).grid(row=6, column=0, columnspan=4, sticky="w", padx=6, pady=2)

        self.dry_run_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Dry run (retrieval only, no Claude calls, free)",
                        variable=self.dry_run_var).grid(row=2, column=0, columnspan=4, sticky="w", padx=6, pady=2)

        ttk.Label(opts, text="Max items per group (blank = no cap):").grid(row=3, column=0, sticky="w", padx=6, pady=2)
        self.max_items_var = tk.StringVar(value="")
        ttk.Entry(opts, textvariable=self.max_items_var, width=8).grid(row=3, column=1, sticky="w", padx=6)

        # Date range (blank = each group's default rolling window back from today)
        ttk.Label(opts, text="Date range (YYYY-MM-DD):").grid(
            row=4, column=0, sticky="w", padx=6, pady=2)
        date_row = ttk.Frame(opts)
        date_row.grid(row=4, column=1, columnspan=3, sticky="w", padx=6)
        ttk.Label(date_row, text="From").pack(side="left")
        self.start_date_var = tk.StringVar(value="")
        ttk.Entry(date_row, textvariable=self.start_date_var, width=12).pack(side="left", padx=(2, 8))
        ttk.Label(date_row, text="To").pack(side="left")
        self.end_date_var = tk.StringVar(value="")
        ttk.Entry(date_row, textvariable=self.end_date_var, width=12).pack(side="left", padx=2)
        ttk.Label(opts, text=f"Leave blank to use the default window: {default_window_note()}.",
                  foreground="#666").grid(row=5, column=0, columnspan=4, sticky="w", padx=6, pady=(0, 2))

        # Run / stop controls
        ctrl = ttk.Frame(self.root)
        ctrl.grid(row=2, column=0, sticky="ew", **pad)
        self.run_btn = ttk.Button(ctrl, text="Run cycle", command=self._run)
        self.run_btn.pack(side="left", padx=2)
        self.stop_btn = ttk.Button(ctrl, text="Stop", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=2)
        self.status_var = tk.StringVar(value="Idle.")
        ttk.Label(ctrl, textvariable=self.status_var).pack(side="left", padx=12)

        # Log pane
        log_frame = ttk.LabelFrame(self.root, text="Output")
        log_frame.grid(row=3, column=0, sticky="nsew", **pad)
        self.log = scrolledtext.ScrolledText(log_frame, width=90, height=18, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True)

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(3, weight=1)

    # --- checkbox helpers -------------------------------------------------
    def _build_group_section(self, parent, title: str, groups: list, cols: int):
        """Build a labeled subsection of disease-group checkboxes with its own
        All / None buttons. Registers each group's BooleanVar in group_vars."""
        frame = ttk.LabelFrame(parent, text=title)
        for i, group in enumerate(groups):
            var = tk.BooleanVar(value=(group.key == "aml"))
            self.group_vars[group.key] = var
            ttk.Checkbutton(frame, text=group.label, variable=var).grid(
                row=i // cols, column=i % cols, sticky="w", padx=6, pady=1)
        keys = [g.key for g in groups]
        sec_btns = ttk.Frame(frame)
        sec_btns.grid(row=(len(groups) // cols) + 1, column=0, columnspan=cols, sticky="w", pady=(4, 2))
        ttk.Button(sec_btns, text="All", width=5, command=lambda: self._set_keys(keys, True)).pack(side="left", padx=2)
        ttk.Button(sec_btns, text="None", width=5, command=lambda: self._set_keys(keys, False)).pack(side="left", padx=2)
        return frame

    def _set_keys(self, keys: list[str], value: bool):
        for k in keys:
            self.group_vars[k].set(value)

    def _select_all(self):
        for var in self.group_vars.values():
            var.set(True)

    def _clear_all(self):
        for var in self.group_vars.values():
            var.set(False)

    # --- run / stop -------------------------------------------------------
    def _selected_groups(self) -> list[str]:
        return [k for k, v in self.group_vars.items() if v.get()]

    def _run(self):
        if self.proc is not None:
            return
        try:
            cmd = build_command(
                self._selected_groups(), self.format_var.get(),
                self.ignore_seen_var.get(), self.dry_run_var.get(),
                self.max_items_var.get(),
                self.start_date_var.get(), self.end_date_var.get(),
                use_llm=self.use_llm_var.get(),
            )
        except ValueError as e:
            self._append(f"{e}\n")
            return

        self._clear_log()
        self._append("$ " + " ".join(cmd) + "\n\n")
        self.run_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status_var.set("Running...")

        threading.Thread(target=self._worker, args=(cmd,), daemon=True).start()

    def _worker(self, cmd: list[str]):
        try:
            self.proc = subprocess.Popen(
                cmd, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            for line in self.proc.stdout:
                self.log_queue.put(line)
            self.proc.wait()
            rc = self.proc.returncode
            self.log_queue.put(f"\n[Finished, exit code {rc}]\n")
            self.log_queue.put(f"__STATUS__{'Done.' if rc == 0 else f'Failed (exit {rc}).'}")
        except Exception as e:  # surface, never swallow
            self.log_queue.put(f"\n[Error launching pipeline: {e}]\n")
            self.log_queue.put("__STATUS__Error.")
        finally:
            self.proc = None
            self.log_queue.put("__DONE__")

    def _stop(self):
        if self.proc is not None:
            self.proc.terminate()
            self._append("\n[Stop requested...]\n")

    # --- log pump ---------------------------------------------------------
    def _drain_log(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                if msg == "__DONE__":
                    self.run_btn.config(state="normal")
                    self.stop_btn.config(state="disabled")
                elif msg.startswith("__STATUS__"):
                    self.status_var.set(msg[len("__STATUS__"):])
                else:
                    self._append(msg)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_log)

    def _append(self, text: str):
        self.log.config(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.config(state="disabled")

    def _clear_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")


def main():
    root = tk.Tk()
    PipelineGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
