"""
Dashboard View
Main device overview with polished cards for each connected drive.
Enhanced with drive management button and macOS-style design.
"""

import threading
import customtkinter as ctk
from typing import Callable, Optional

from core.device_scanner import DeviceInfo, DeviceScanner
from core.corruption_detector import CorruptionDetector, HealthStatus, HealthReport
from core.drive_manager import DriveManager


class DeviceCard(ctk.CTkFrame):
    """A polished card widget displaying info about a single device."""

    def __init__(self, master, device: DeviceInfo,
                 on_scan: Callable, on_health_check: Callable,
                 on_hex_view: Callable, on_manage: Callable, **kwargs):
        super().__init__(master, corner_radius=16, **kwargs)
        self.device = device
        self.on_scan = on_scan
        self.on_health_check = on_health_check
        self.on_hex_view = on_hex_view
        self.on_manage = on_manage
        self._health_report: Optional[HealthReport] = None

        self.configure(
            fg_color=("gray90", "gray17"),
            border_width=1,
            border_color=("gray78", "gray28"),
        )

        self._build_ui()

    def _build_ui(self):
        # ── Header row ──
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(16, 6))

        # Drive icon — color-coded by type
        icon = "🔌" if self.device.bus_protocol.upper() == "USB" else "💾"
        ctk.CTkLabel(
            header, text=icon,
            font=ctk.CTkFont(size=34),
        ).pack(side="left", padx=(0, 12))

        name_frame = ctk.CTkFrame(header, fg_color="transparent")
        name_frame.pack(side="left", fill="x", expand=True)

        self.name_label = ctk.CTkLabel(
            name_frame,
            text=self.device.display_name,
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        )
        self.name_label.pack(fill="x")

        proto = self.device.bus_protocol or "Local"
        self.sub_label = ctk.CTkLabel(
            name_frame,
            text=f"{self.device.identifier}  •  {proto}  •  {self.device.size_human}",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60"),
            anchor="w",
        )
        self.sub_label.pack(fill="x")

        # Health badge
        self.health_badge = ctk.CTkLabel(
            header, text="  ⚪ Unknown  ",
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=10,
            fg_color=("gray82", "gray28"),
            padx=8, pady=3,
        )
        self.health_badge.pack(side="right")

        # ── Usage bar (if mounted) ──
        if self.device.mount_point:
            usage = DriveManager.get_disk_usage(self.device.mount_point)
            if usage:
                usage_frame = ctk.CTkFrame(self, fg_color="transparent")
                usage_frame.pack(fill="x", padx=18, pady=(4, 2))

                bar = ctk.CTkProgressBar(
                    usage_frame, height=8, corner_radius=4,
                    progress_color=("#3b82f6", "#2563eb"),
                )
                bar.pack(fill="x")
                bar.set(usage.percent_used / 100)

                if usage.percent_used > 90:
                    bar.configure(progress_color=("#ef4444", "#dc2626"))
                elif usage.percent_used > 70:
                    bar.configure(progress_color=("#f59e0b", "#d97706"))

                usage_text = ctk.CTkFrame(usage_frame, fg_color="transparent")
                usage_text.pack(fill="x")
                ctk.CTkLabel(
                    usage_text,
                    text=f"{usage.used_human} used",
                    font=ctk.CTkFont(size=10),
                    text_color=("gray45", "gray55"), anchor="w",
                ).pack(side="left")
                ctk.CTkLabel(
                    usage_text,
                    text=f"{usage.free_human} free",
                    font=ctk.CTkFont(size=10),
                    text_color=("gray45", "gray55"), anchor="e",
                ).pack(side="right")

        # ── Info chips ──
        chips = ctk.CTkFrame(self, fg_color="transparent")
        chips.pack(fill="x", padx=18, pady=(6, 4))

        infos = [
            ("FS", self.device.filesystem or "—"),
            ("Mount", self.device.mount_point or "Not mounted"),
        ]
        for label, value in infos:
            chip = ctk.CTkFrame(chips, fg_color=("gray85", "gray22"),
                                corner_radius=8)
            chip.pack(side="left", padx=(0, 6))
            ctk.CTkLabel(
                chip, text=f" {label}: ",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=("gray45", "gray55"),
            ).pack(side="left", padx=(6, 0))
            ctk.CTkLabel(
                chip, text=f"{value} ",
                font=ctk.CTkFont(size=10),
            ).pack(side="left", padx=(0, 6))

        # ── Partitions ──
        if self.device.partitions:
            part_frame = ctk.CTkFrame(self, fg_color=("gray85", "gray20"),
                                      corner_radius=10)
            part_frame.pack(fill="x", padx=18, pady=(6, 4))

            ctk.CTkLabel(
                part_frame,
                text=f"  📂 {len(self.device.partitions)} Partition(s)",
                font=ctk.CTkFont(size=11, weight="bold"),
                anchor="w",
            ).pack(fill="x", padx=10, pady=(8, 3))

            for p in self.device.partitions[:5]:
                mount_str = f" → {p.mount_point}" if p.mount_point else ""
                ctk.CTkLabel(
                    part_frame,
                    text=f"     {p.identifier}  •  {p.name}  •  {p.size_human}  •  {p.filesystem}{mount_str}",
                    font=ctk.CTkFont(size=10),
                    text_color=("gray40", "gray60"),
                    anchor="w",
                ).pack(fill="x", padx=10)
            ctk.CTkFrame(part_frame, height=6, fg_color="transparent").pack()

        # ── Health details (hidden initially) ──
        self.health_details_frame = ctk.CTkFrame(
            self, fg_color=("gray85", "gray20"), corner_radius=10
        )
        self.health_details_text = ctk.CTkTextbox(
            self.health_details_frame, height=110,
            font=ctk.CTkFont(family="Menlo", size=10),
            fg_color="transparent", state="disabled",
        )
        self.health_details_text.pack(fill="both", expand=True, padx=8, pady=8)

        # ── Health check progress indicator ──
        self.health_progress = ctk.CTkProgressBar(
            self, height=4, corner_radius=2,
            progress_color=("#22c55e", "#16a34a"),
            mode="indeterminate",
        )

        # ── Action buttons ──
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=18, pady=(8, 16))

        buttons = [
            ("🔍 Scan", "#2563eb", "#1d4ed8", lambda: self.on_scan(self.device)),
            ("🩺 Health", "#059669", "#047857", self._start_health_check),
            ("🛠️ Manage", "#7c3aed", "#6d28d9", lambda: self.on_manage(self.device)),
            ("🔢 Hex", "#d97706", "#b45309", lambda: self.on_hex_view(self.device)),
        ]

        for text, fg, hover, cmd in buttons:
            ctk.CTkButton(
                btn_frame, text=text,
                font=ctk.CTkFont(size=12, weight="bold"),
                height=36, corner_radius=10,
                fg_color=fg, hover_color=hover,
                command=cmd,
            ).pack(side="left", expand=True, fill="x", padx=2)

    def _start_health_check(self):
        """Run health check in a background thread with progress indicator."""
        self.health_badge.configure(text="  🔄 Checking...  ",
                                    fg_color=("gray70", "gray35"))
        self.health_progress.pack(fill="x", padx=18, pady=(0, 4),
                                  before=self.health_details_frame)
        self.health_progress.start()

        def _run():
            detector = CorruptionDetector(
                self.device.identifier,
                self.device.device_path,
                self.device.raw_device_path,
                self.device.size_bytes,
            )
            report = detector.full_check()
            self._health_report = report
            self.after(0, lambda: self._update_health(report))

        threading.Thread(target=_run, daemon=True).start()

    def _update_health(self, report: HealthReport):
        """Update UI with health check results."""
        if not self.winfo_exists():
            return
            
        try:
            self.health_progress.stop()
            self.health_progress.pack_forget()
        except Exception:
            pass


        colors = {
            HealthStatus.HEALTHY: (("#dcfce7", "#14532d"), "  🟢 Healthy  "),
            HealthStatus.WARNING: (("#fef9c3", "#713f12"), "  🟡 Warning  "),
            HealthStatus.CORRUPTED: (("#fecaca", "#7f1d1d"), "  🔴 Corrupted  "),
            HealthStatus.UNKNOWN: (("gray80", "gray30"), "  ⚪ Unknown  "),
        }
        color, text = colors.get(report.status, colors[HealthStatus.UNKNOWN])
        self.health_badge.configure(text=text, fg_color=color)

        self.health_details_frame.pack(fill="x", padx=18, pady=(0, 8))
        self.health_details_text.configure(state="normal")
        self.health_details_text.delete("1.0", "end")
        self.health_details_text.insert("end", report.summary + "\n\n")
        for line in report.details:
            self.health_details_text.insert("end", line + "\n")
        self.health_details_text.configure(state="disabled")

        if report.status == HealthStatus.CORRUPTED:
            self.configure(border_color=("#ef4444", "#dc2626"))
        elif report.status == HealthStatus.WARNING:
            self.configure(border_color=("#f59e0b", "#d97706"))
        elif report.status == HealthStatus.HEALTHY:
            self.configure(border_color=("#22c55e", "#16a34a"))


class DashboardView(ctk.CTkScrollableFrame):
    """Main dashboard showing all connected devices."""

    def __init__(self, master, on_scan: Callable, on_hex_view: Callable,
                 on_manage: Callable,
                 include_internal: bool = False, **kwargs):
        super().__init__(master, **kwargs)
        self.on_scan = on_scan
        self.on_hex_view = on_hex_view
        self.on_manage = on_manage
        self.include_internal = include_internal
        self._device_cards: list = []

        self.configure(fg_color="transparent")
        self._build_header()
        self.refresh_devices()

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            header,
            text="📡 Connected Devices",
            font=ctk.CTkFont(size=24, weight="bold"),
            anchor="w",
        ).pack(side="left")

        self.refresh_btn = ctk.CTkButton(
            header, text="🔄 Refresh", width=100,
            font=ctk.CTkFont(size=13),
            height=32, corner_radius=8,
            fg_color=("gray75", "gray30"),
            hover_color=("gray65", "gray40"),
            command=self.refresh_devices,
        )
        self.refresh_btn.pack(side="right")

        self.status_label = ctk.CTkLabel(
            header, text="",
            font=ctk.CTkFont(size=13),
            text_color=("gray50", "gray55"),
        )
        self.status_label.pack(side="right", padx=12)

        # Scanning progress indicator
        self.scan_progress = ctk.CTkProgressBar(
            self, height=4, corner_radius=2,
            progress_color=("#3b82f6", "#2563eb"),
            mode="indeterminate",
        )

    def refresh_devices(self):
        """Re-scan for devices and rebuild cards."""
        for card in self._device_cards:
            card.destroy()
        self._device_cards.clear()

        self.status_label.configure(text="Scanning...")
        self.scan_progress.pack(fill="x", pady=(0, 8))
        self.scan_progress.start()

        def _scan():
            scanner = DeviceScanner(include_internal=self.include_internal)
            devices = scanner.scan()
            if self.winfo_exists():
                self.after(0, lambda: self._show_devices(devices))

        threading.Thread(target=_scan, daemon=True).start()

    def _show_devices(self, devices: list[DeviceInfo]):
        try:
            if not self.winfo_exists():
                return
                
            try:
                self.scan_progress.stop()
                self.scan_progress.pack_forget()
            except Exception:
                pass

            if not getattr(self, "status_label", None) or not self.status_label.winfo_exists():
                return

            if not devices:
                self.status_label.configure(text="No external devices found")
                empty = ctk.CTkFrame(self, fg_color=("gray92", "gray15"),
                                     corner_radius=16, height=220)
                empty.pack(fill="x", pady=20)
                empty.pack_propagate(False)
                ctk.CTkLabel(
                    empty, text="🔌",
                    font=ctk.CTkFont(size=52),
                ).pack(pady=(35, 8))
                ctk.CTkLabel(
                    empty,
                    text="No external drives detected.\nConnect a device and click Refresh.",
                    font=ctk.CTkFont(size=14),
                    text_color=("gray50", "gray55"),
                    justify="center",
                ).pack()
                self._device_cards.append(empty)
                return

            self.status_label.configure(text=f"{len(devices)} device(s) found")
            for device in devices:
                card = DeviceCard(
                    self, device,
                    on_scan=self.on_scan,
                    on_health_check=lambda d: None,
                    on_hex_view=self.on_hex_view,
                    on_manage=self.on_manage,
                )
                card.pack(fill="x", pady=6)
                self._device_cards.append(card)
        except Exception:
            pass  # Widget was destroyed before callback — safe to ignore

    def set_include_internal(self, val: bool):
        self.include_internal = val
        self.refresh_devices()
