"""
Drive Management View
Full-featured drive management panel: format, rename, mount/unmount, eject, repair, usage.
"""

import threading
import customtkinter as ctk
from tkinter import messagebox
from typing import Callable, Optional

from core.device_scanner import DeviceInfo
from core.drive_manager import DriveManager, FilesystemType, OperationResult, DiskUsageInfo


class DriveManageView(ctk.CTkFrame):
    """Drive management panel with all disk operations."""

    def __init__(self, master, device: DeviceInfo,
                 on_back: Callable, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.device = device
        self.on_back = on_back

        self._build_ui()
        self._load_info()

    def _build_ui(self):
        # ── Header ──
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 10))

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
            text=f"🛠️ Manage: {self.device.display_name}",
            font=ctk.CTkFont(size=22, weight="bold"),
            anchor="w",
        ).pack(side="left", padx=12)

        # ── Main scrollable area ──
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # ═══ Disk Usage ═══
        self._section(scroll, "📊  Disk Usage")

        usage_card = ctk.CTkFrame(scroll, fg_color=("gray90", "gray17"),
                                  corner_radius=14)
        usage_card.pack(fill="x", pady=(0, 16))

        self.usage_bar = ctk.CTkProgressBar(
            usage_card, height=22, corner_radius=11,
            progress_color=("#3b82f6", "#2563eb"),
        )
        self.usage_bar.pack(fill="x", padx=16, pady=(16, 8))
        self.usage_bar.set(0)

        self.usage_labels_frame = ctk.CTkFrame(usage_card, fg_color="transparent")
        self.usage_labels_frame.pack(fill="x", padx=16, pady=(0, 14))

        self.used_label = ctk.CTkLabel(
            self.usage_labels_frame, text="Used: —",
            font=ctk.CTkFont(size=13), anchor="w",
        )
        self.used_label.pack(side="left")

        self.free_label = ctk.CTkLabel(
            self.usage_labels_frame, text="Free: —",
            font=ctk.CTkFont(size=13), anchor="e",
        )
        self.free_label.pack(side="right")

        self.total_label = ctk.CTkLabel(
            self.usage_labels_frame, text="Total: —",
            font=ctk.CTkFont(size=13),
            text_color=("gray50", "gray55"),
        )
        self.total_label.pack()

        # ═══ Quick Actions ═══
        self._section(scroll, "⚡  Quick Actions")

        actions_frame = ctk.CTkFrame(scroll, fg_color=("gray90", "gray17"),
                                     corner_radius=14)
        actions_frame.pack(fill="x", pady=(0, 16))

        actions_grid = ctk.CTkFrame(actions_frame, fg_color="transparent")
        actions_grid.pack(fill="x", padx=12, pady=12)

        actions = [
            ("📛 Rename", "#2563eb", self._action_rename),
            ("📤 Unmount", "#7c3aed", self._action_unmount),
            ("📥 Mount", "#059669", self._action_mount),
            ("⏏️ Eject", "#f59e0b", self._action_eject),
            ("🔧 Repair", "#06b6d4", self._action_repair),
            ("📋 Detailed Info", "#6366f1", self._action_info),
        ]

        for i, (text, color, cmd) in enumerate(actions):
            btn = ctk.CTkButton(
                actions_grid, text=text,
                font=ctk.CTkFont(size=13, weight="bold"),
                height=44, corner_radius=12,
                fg_color=color,
                hover_color=self._darken(color),
                command=cmd,
            )
            row, col = divmod(i, 3)
            btn.grid(row=row, column=col, padx=4, pady=4, sticky="ew")

        actions_grid.grid_columnconfigure((0, 1, 2), weight=1)

        # ═══ Format / Erase ═══
        self._section(scroll, "🗑️  Format & Erase")

        format_card = ctk.CTkFrame(scroll, fg_color=("gray90", "gray17"),
                                   corner_radius=14)
        format_card.pack(fill="x", pady=(0, 16))

        # Warning banner
        warn = ctk.CTkFrame(format_card, fg_color=("#fef2f2", "#3b1111"),
                            corner_radius=10)
        warn.pack(fill="x", padx=14, pady=(14, 8))
        ctk.CTkLabel(
            warn,
            text="⚠️  Formatting will PERMANENTLY DELETE all data on this drive!",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#dc2626", "#f87171"),
        ).pack(padx=12, pady=8)

        fmt_inner = ctk.CTkFrame(format_card, fg_color="transparent")
        fmt_inner.pack(fill="x", padx=14, pady=(4, 14))

        # Filesystem selector
        fs_row = ctk.CTkFrame(fmt_inner, fg_color="transparent")
        fs_row.pack(fill="x", pady=4)

        ctk.CTkLabel(
            fs_row, text="Filesystem:",
            font=ctk.CTkFont(size=13),
        ).pack(side="left")

        self.fs_var = ctk.StringVar(value="ExFAT")
        ctk.CTkOptionMenu(
            fs_row,
            values=["ExFAT", "FAT32", "APFS", "HFS+"],
            variable=self.fs_var,
            font=ctk.CTkFont(size=12),
            width=140,
        ).pack(side="right")

        # Name entry
        name_row = ctk.CTkFrame(fmt_inner, fg_color="transparent")
        name_row.pack(fill="x", pady=4)

        ctk.CTkLabel(
            name_row, text="Volume Name:",
            font=ctk.CTkFont(size=13),
        ).pack(side="left")

        self.format_name_entry = ctk.CTkEntry(
            name_row, width=180,
            font=ctk.CTkFont(size=13),
            height=32, corner_radius=8,
            placeholder_text="Untitled",
        )
        self.format_name_entry.pack(side="right")

        # Format buttons
        fmt_btn_row = ctk.CTkFrame(fmt_inner, fg_color="transparent")
        fmt_btn_row.pack(fill="x", pady=(8, 0))

        self.format_btn = ctk.CTkButton(
            fmt_btn_row,
            text="🗑️  Erase Entire Disk",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44, corner_radius=12,
            fg_color=("#dc2626", "#b91c1c"),
            hover_color=("#b91c1c", "#991b1b"),
            command=self._action_format,
        )
        self.format_btn.pack(fill="x")

        # ═══ S.M.A.R.T. Status ═══
        self._section(scroll, "💚  S.M.A.R.T. Status")

        smart_card = ctk.CTkFrame(scroll, fg_color=("gray90", "gray17"),
                                  corner_radius=14)
        smart_card.pack(fill="x", pady=(0, 16))

        self.smart_label = ctk.CTkLabel(
            smart_card, text="Loading...",
            font=ctk.CTkFont(size=14),
            anchor="w",
        )
        self.smart_label.pack(padx=16, pady=14, fill="x")

        # ═══ Operation Log ═══
        self._section(scroll, "📋  Operation Log")

        self.log_text = ctk.CTkTextbox(
            scroll, height=150,
            font=ctk.CTkFont(family="Menlo", size=11),
            fg_color=("gray95", "gray10"),
            corner_radius=12,
            state="disabled",
        )
        self.log_text.pack(fill="x", pady=(0, 16))

        # ── Progress bar for operations ──
        self.op_progress = ctk.CTkProgressBar(
            self, height=6, corner_radius=3,
            progress_color=("#3b82f6", "#2563eb"),
            mode="indeterminate",
        )

    def _section(self, parent, title: str):
        ctk.CTkLabel(
            parent, text=title,
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(12, 6))

    def _darken(self, hex_color: str) -> str:
        """Slightly darken a hex color."""
        r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
        r, g, b = max(0, r - 30), max(0, g - 30), max(0, b - 30)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _log(self, msg: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _show_progress(self):
        self.op_progress.pack(fill="x", pady=(0, 4), side="bottom")
        self.op_progress.start()

    def _hide_progress(self):
        self.op_progress.stop()
        self.op_progress.pack_forget()

    def _load_info(self):
        """Load disk usage and S.M.A.R.T. status."""
        def _work():
            usage = None
            if self.device.mount_point:
                usage = DriveManager.get_disk_usage(self.device.mount_point)
            smart = DriveManager.get_smart_status(self.device.identifier)
            self.after(0, lambda: self._display_info(usage, smart))

        threading.Thread(target=_work, daemon=True).start()

    def _display_info(self, usage: Optional[DiskUsageInfo], smart: Optional[str]):
        if usage:
            self.usage_bar.set(usage.percent_used / 100)
            self.used_label.configure(text=f"Used: {usage.used_human}")
            self.free_label.configure(text=f"Free: {usage.free_human}")
            self.total_label.configure(text=f"Total: {usage.total_human}")

            # Color code the bar
            if usage.percent_used > 90:
                self.usage_bar.configure(progress_color=("#ef4444", "#dc2626"))
            elif usage.percent_used > 70:
                self.usage_bar.configure(progress_color=("#f59e0b", "#d97706"))
        else:
            self.used_label.configure(text="Not mounted — usage unavailable")

        if smart:
            icon = "✅" if smart == "Verified" else "⚠️"
            self.smart_label.configure(text=f"{icon}  S.M.A.R.T. Status: {smart}")

    def _op_done(self, result: OperationResult, refresh: bool = False):
        self._hide_progress()
        self._log(f"{result.status_icon}  {result.message}")
        if result.error:
            self._log(f"   Error: {result.error}")
        if result.raw_output:
            for line in result.raw_output.strip().splitlines()[:5]:
                self._log(f"   {line.strip()}")
        if refresh:
            self._load_info()

    def _action_rename(self):
        dialog = ctk.CTkInputDialog(
            text=f"New name for {self.device.display_name}:",
            title="Rename Volume",
        )
        new_name = dialog.get_input()
        if not new_name:
            return

        self._show_progress()
        self._log(f"Renaming {self.device.identifier} → {new_name}...")

        def _done(r):
            self.after(0, lambda: self._op_done(r, refresh=True))

        # Find the right partition to rename
        target = self.device.identifier
        for p in self.device.partitions:
            if p.mount_point:
                target = p.identifier
                break

        DriveManager.run_async(
            DriveManager.rename_volume, target, new_name,
            done_callback=_done,
        )

    def _action_unmount(self):
        target = self.device.identifier
        for p in self.device.partitions:
            if p.mount_point:
                target = p.identifier
                break

        self._show_progress()
        self._log(f"Unmounting {target}...")

        def _done(r):
            self.after(0, lambda: self._op_done(r, refresh=True))

        DriveManager.run_async(
            DriveManager.unmount_volume, target,
            done_callback=_done,
        )

    def _action_mount(self):
        target = self.device.identifier
        for p in self.device.partitions:
            if not p.mount_point:
                target = p.identifier
                break

        self._show_progress()
        self._log(f"Mounting {target}...")

        def _done(r):
            self.after(0, lambda: self._op_done(r, refresh=True))

        DriveManager.run_async(
            DriveManager.mount_volume, target,
            done_callback=_done,
        )

    def _action_eject(self):
        confirm = messagebox.askyesno(
            "Eject Drive",
            f"Eject {self.device.display_name}?\n\n"
            "The drive will be safely disconnected.",
        )
        if not confirm:
            return

        self._show_progress()
        self._log(f"Ejecting {self.device.identifier}...")

        def _done(r):
            self.after(0, lambda: self._op_done(r))

        DriveManager.run_async(
            DriveManager.eject_disk, self.device.identifier,
            done_callback=_done,
        )

    def _action_repair(self):
        self._show_progress()
        self._log(f"Repairing {self.device.identifier}...")

        target = self.device.identifier
        for p in self.device.partitions:
            if p.mount_point:
                target = p.identifier
                break

        def _done(r):
            self.after(0, lambda: self._op_done(r, refresh=True))

        DriveManager.run_async(
            DriveManager.repair_volume, target,
            done_callback=_done,
        )

    def _action_info(self):
        """Show detailed disk info in the log."""
        self._show_progress()
        self._log("─── Detailed Disk Info ───")

        def _work():
            info = DriveManager.get_disk_info_detailed(self.device.identifier)
            self.after(0, lambda: self._display_detailed_info(info))

        threading.Thread(target=_work, daemon=True).start()

    def _display_detailed_info(self, info: dict):
        self._hide_progress()
        keys_of_interest = [
            "DeviceIdentifier", "DeviceNode", "VolumeName", "VolumeUUID",
            "FilesystemType", "FilesystemName", "TotalSize", "DeviceBlockSize",
            "BusProtocol", "MediaName", "MediaType", "Removable",
            "RemovableMedia", "Internal", "SMARTStatus",
            "IORegistryEntryName", "Content",
        ]
        for key in keys_of_interest:
            if key in info:
                val = info[key]
                if key == "TotalSize":
                    val = f"{val:,} bytes ({self._human_size(val)})"
                self._log(f"  {key}: {val}")

    @staticmethod
    def _human_size(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def _action_format(self):
        """Format the entire disk — with confirmation dialog."""
        fs_name = self.fs_var.get()
        vol_name = self.format_name_entry.get().strip() or "Untitled"

        confirm = messagebox.askyesno(
            "⚠️ Erase Disk",
            f"Are you sure you want to ERASE {self.device.display_name}?\n\n"
            f"Filesystem: {fs_name}\n"
            f"Name: {vol_name}\n\n"
            "⚠️ ALL DATA WILL BE PERMANENTLY DELETED!",
            icon="warning",
        )
        if not confirm:
            return

        # Double confirm
        confirm2 = messagebox.askyesno(
            "⚠️ FINAL WARNING",
            f"This is your LAST CHANCE.\n\n"
            f"Erase ALL data on {self.device.display_name}?",
            icon="warning",
        )
        if not confirm2:
            return

        fs_map = {
            "ExFAT": FilesystemType.EXFAT,
            "FAT32": FilesystemType.FAT32,
            "APFS": FilesystemType.APFS,
            "HFS+": FilesystemType.HFS_PLUS,
        }
        fs_type = fs_map.get(fs_name, FilesystemType.EXFAT)

        self._show_progress()
        self._log(f"⏳ Erasing {self.device.identifier} as {fs_name} ({vol_name})...")

        def _done(r):
            self.after(0, lambda: self._op_done(r, refresh=True))

        DriveManager.run_async(
            DriveManager.erase_disk, self.device.identifier, fs_type, vol_name,
            done_callback=_done,
        )
