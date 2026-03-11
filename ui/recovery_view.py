"""
Recovery View
UI for recovering selected files from a scanned device.
"""

import os
import subprocess
import threading
import customtkinter as ctk
from tkinter import filedialog
from typing import Callable, Optional

from core.device_scanner import DeviceInfo
from core.file_carver import CarvedFile
from core.recovery_engine import RecoveryEngine, RecoveryProgress


class RecoveryView(ctk.CTkFrame):
    """View for recovering files to disk."""

    def __init__(self, master, device: DeviceInfo,
                 files: list[CarvedFile],
                 on_back: Callable, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.device = device
        self.files = files
        self.on_back = on_back
        self._engine: Optional[RecoveryEngine] = None
        self._output_dir = os.path.expanduser("~/Desktop/Recovered Files")

        self._build_ui()

    def _build_ui(self):
        # ── Header ──
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 12))

        ctk.CTkButton(
            header, text="← Back", width=80,
            font=ctk.CTkFont(size=13),
            fg_color="transparent",
            hover_color=("gray80", "gray30"),
            text_color=("gray30", "gray70"),
            command=self.on_back,
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text="📥 File Recovery",
            font=ctk.CTkFont(size=22, weight="bold"),
            anchor="w",
        ).pack(side="left", padx=12)

        # ── Summary ──
        summary = ctk.CTkFrame(self, fg_color=("gray90", "gray17"),
                               corner_radius=14)
        summary.pack(fill="x", pady=(0, 12))

        stats_row = ctk.CTkFrame(summary, fg_color="transparent")
        stats_row.pack(fill="x", padx=16, pady=14)

        total_size = sum(f.size for f in self.files)
        stats = [
            ("Files Selected", str(len(self.files)), "📁"),
            ("Total Size", self._human_size(total_size), "💾"),
            ("Device", self.device.display_name, "🔌"),
            ("Categories", str(len(set(f.category for f in self.files))), "📂"),
        ]

        for label, value, icon in stats:
            card = ctk.CTkFrame(stats_row, fg_color=("gray85", "gray22"),
                                corner_radius=10)
            card.pack(side="left", expand=True, fill="x", padx=4)

            ctk.CTkLabel(
                card, text=icon,
                font=ctk.CTkFont(size=24),
            ).pack(pady=(10, 2))

            ctk.CTkLabel(
                card, text=value,
                font=ctk.CTkFont(size=18, weight="bold"),
            ).pack()

            ctk.CTkLabel(
                card, text=label,
                font=ctk.CTkFont(size=11),
                text_color=("gray50", "gray55"),
            ).pack(pady=(0, 10))

        # ── Output directory ──
        dir_frame = ctk.CTkFrame(self, fg_color=("gray90", "gray17"),
                                 corner_radius=14)
        dir_frame.pack(fill="x", pady=(0, 12))

        dir_row = ctk.CTkFrame(dir_frame, fg_color="transparent")
        dir_row.pack(fill="x", padx=16, pady=14)

        ctk.CTkLabel(
            dir_row, text="Output Directory:",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="left")

        self.dir_entry = ctk.CTkEntry(
            dir_row, font=ctk.CTkFont(size=13),
            height=34, corner_radius=8,
        )
        self.dir_entry.pack(side="left", expand=True, fill="x", padx=8)
        self.dir_entry.insert(0, self._output_dir)

        ctk.CTkButton(
            dir_row, text="Browse...", width=90,
            font=ctk.CTkFont(size=12),
            height=34, corner_radius=8,
            fg_color=("gray75", "gray30"),
            hover_color=("gray65", "gray40"),
            command=self._browse_dir,
        ).pack(side="right")

        # ── Start button ──
        self.start_btn = ctk.CTkButton(
            self, text="🚀  Start Recovery",
            font=ctk.CTkFont(size=16, weight="bold"),
            height=50, corner_radius=14,
            fg_color=("#059669", "#047857"),
            hover_color=("#047857", "#065f46"),
            command=self._start_recovery,
        )
        self.start_btn.pack(fill="x", pady=(0, 12))

        # ── Progress ──
        progress_frame = ctk.CTkFrame(self, fg_color=("gray90", "gray17"),
                                      corner_radius=14)
        progress_frame.pack(fill="x", pady=(0, 12))

        self.progress_bar = ctk.CTkProgressBar(
            progress_frame, height=18, corner_radius=9,
            progress_color=("#059669", "#10b981"),
        )
        self.progress_bar.pack(fill="x", padx=16, pady=(16, 8))
        self.progress_bar.set(0)

        prog_row = ctk.CTkFrame(progress_frame, fg_color="transparent")
        prog_row.pack(fill="x", padx=16, pady=(0, 14))

        self.progress_label = ctk.CTkLabel(
            prog_row, text="Ready to recover",
            font=ctk.CTkFont(size=13),
            anchor="w",
        )
        self.progress_label.pack(side="left")

        self.file_label = ctk.CTkLabel(
            prog_row, text="",
            font=ctk.CTkFont(size=12),
            text_color=("gray50", "gray55"),
            anchor="e",
        )
        self.file_label.pack(side="right")

        # ── Results list ──
        self.results_frame = ctk.CTkScrollableFrame(
            self, fg_color=("gray92", "gray14"),
            corner_radius=12,
        )
        self.results_frame.pack(fill="both", expand=True)

        self._result_rows: list = []

        # ── Bottom bar (hidden until complete) ──
        self.bottom_bar = ctk.CTkFrame(self, fg_color="transparent")

        self.open_folder_btn = ctk.CTkButton(
            self.bottom_bar, text="📂  Open Folder",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40, corner_radius=10,
            fg_color=("#2563eb", "#1d4ed8"),
            hover_color=("#1e40af", "#1e3a8a"),
            command=self._open_output_folder,
        )
        self.open_folder_btn.pack(side="left", expand=True, fill="x", padx=(0, 4))

        self.report_btn = ctk.CTkButton(
            self.bottom_bar, text="📋  View Report",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40, corner_radius=10,
            fg_color=("#7c3aed", "#6d28d9"),
            hover_color=("#6d28d9", "#5b21b6"),
            command=self._open_report,
        )
        self.report_btn.pack(side="left", expand=True, fill="x", padx=(4, 0))

    def _browse_dir(self):
        path = filedialog.askdirectory(
            title="Choose Output Directory",
            initialdir=os.path.expanduser("~/Desktop"),
        )
        if path:
            self._output_dir = path
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, path)

    def _start_recovery(self):
        self._output_dir = self.dir_entry.get().strip()
        if not self._output_dir:
            self._output_dir = os.path.expanduser("~/Desktop/Recovered Files")

        # Determine device path
        device_path = self.device.raw_device_path
        for p in self.device.partitions:
            if p.mount_point:
                device_path = f"/dev/r{p.identifier}"
                break

        self._engine = RecoveryEngine(device_path)

        self.start_btn.configure(state="disabled")
        self.progress_bar.set(0)

        # Clear results
        for w in self._result_rows:
            w.destroy()
        self._result_rows.clear()

        self._engine.recover_async(
            files=self.files,
            output_dir=self._output_dir,
            progress_callback=lambda p: self.after(0, lambda p=p: self._update_progress(p)),
            done_callback=lambda p: self.after(0, lambda p=p: self._recovery_complete(p)),
        )

    def _update_progress(self, progress: RecoveryProgress):
        self.progress_bar.set(progress.progress_fraction)
        self.progress_label.configure(
            text=f"{progress.completed_files}/{progress.total_files} files"
        )
        self.file_label.configure(text=progress.current_file)

        # Add result rows as they come in
        while len(self._result_rows) < len(progress.results):
            idx = len(self._result_rows)
            r = progress.results[idx]

            bg = ("gray95", "gray16") if idx % 2 == 0 else ("gray90", "gray19")
            row = ctk.CTkFrame(self.results_frame, fg_color=bg,
                               corner_radius=6, height=28)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            ctk.CTkLabel(
                row, text=r.status_icon, width=30,
                font=ctk.CTkFont(size=14),
            ).pack(side="left", padx=8)

            name = os.path.basename(r.output_path) if r.output_path else "—"
            ctk.CTkLabel(
                row, text=name,
                font=ctk.CTkFont(size=12),
                anchor="w",
            ).pack(side="left", fill="x", expand=True)

            ctk.CTkLabel(
                row, text=r.carved_file.size_human,
                font=ctk.CTkFont(size=11),
                text_color=("gray50", "gray55"),
                width=80,
            ).pack(side="right", padx=8)

            if r.error:
                ctk.CTkLabel(
                    row, text=r.error,
                    font=ctk.CTkFont(size=10),
                    text_color="#ef4444", width=200, anchor="e",
                ).pack(side="right", padx=4)

            self._result_rows.append(row)

    def _recovery_complete(self, progress: RecoveryProgress):
        self.start_btn.configure(state="normal")
        self.progress_bar.set(1.0)
        self.progress_label.configure(
            text=(f"✅ Recovery complete — "
                  f"{progress.success_count} recovered, "
                  f"{progress.fail_count} failed")
        )
        self.file_label.configure(
            text=f"Total: {self._human_size(progress.bytes_recovered)}"
        )

        self.bottom_bar.pack(fill="x", pady=(12, 0))

    def _open_output_folder(self):
        if os.path.isdir(self._output_dir):
            subprocess.run(["open", self._output_dir])

    def _open_report(self):
        report_path = os.path.join(self._output_dir, "recovery_report.txt")
        if os.path.exists(report_path):
            subprocess.run(["open", report_path])

    @staticmethod
    def _human_size(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
