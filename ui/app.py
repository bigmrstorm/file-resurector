"""
File Resurrector — Main Application
Ties together all views with a polished sidebar navigation.
"""

import customtkinter as ctk
from typing import Optional

from core.device_scanner import DeviceInfo
from core.file_carver import CarvedFile
from ui.dashboard_view import DashboardView
from ui.scan_view import ScanView
from ui.recovery_view import RecoveryView
from ui.hex_viewer import HexViewer
from ui.drive_manage_view import DriveManageView
from ui.settings_view import SettingsView, load_settings, save_settings


class SidebarButton(ctk.CTkButton):
    """A styled sidebar navigation button."""

    def __init__(self, master, text: str, icon: str, command=None, **kwargs):
        super().__init__(
            master,
            text=f"  {icon}  {text}",
            font=ctk.CTkFont(size=14),
            height=42,
            corner_radius=10,
            anchor="w",
            fg_color="transparent",
            text_color=("gray30", "gray75"),
            hover_color=("gray82", "gray22"),
            command=command,
            **kwargs,
        )
        self._is_active = False

    def set_active(self, active: bool):
        self._is_active = active
        if active:
            self.configure(
                fg_color=("#2563eb", "#1e40af"),
                text_color="white",
                hover_color=("#1d4ed8", "#1e3a8a"),
            )
        else:
            self.configure(
                fg_color="transparent",
                text_color=("gray30", "gray75"),
                hover_color=("gray82", "gray22"),
            )


class App(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        # ── Settings ──
        self.settings = load_settings()
        ctk.set_appearance_mode(self.settings.get("theme", "dark"))

        # ── Window ──
        self.title("File Resurrector")
        self.geometry("1280x820")
        self.minsize(1000, 640)

        try:
            self.configure(fg_color=("gray96", "gray8"))
        except Exception:
            pass

        # ── Layout ──
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ═══ Sidebar ═══
        self.sidebar = ctk.CTkFrame(
            self, width=230,
            fg_color=("gray93", "gray11"),
            corner_radius=0,
        )
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsw")
        self.sidebar.grid_propagate(False)

        # ── Logo ──
        logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo_frame.pack(fill="x", padx=18, pady=(22, 4))

        ctk.CTkLabel(
            logo_frame, text="🔬",
            font=ctk.CTkFont(size=36),
        ).pack(side="left")

        title_frame = ctk.CTkFrame(logo_frame, fg_color="transparent")
        title_frame.pack(side="left", padx=10)

        ctk.CTkLabel(
            title_frame, text="File Resurrector",
            font=ctk.CTkFont(size=17, weight="bold"),
            anchor="w",
        ).pack(fill="x")

        ctk.CTkLabel(
            title_frame, text="Recovery & Disk Tool",
            font=ctk.CTkFont(size=10),
            text_color=("gray50", "gray50"),
            anchor="w",
        ).pack(fill="x")

        # ── Divider ──
        ctk.CTkFrame(
            self.sidebar, height=1,
            fg_color=("gray80", "gray22"),
        ).pack(fill="x", padx=18, pady=14)

        # ── Navigation ──
        self.nav_buttons: dict[str, SidebarButton] = {}
        nav_items = [
            ("dashboard", "Devices", "📡"),
            ("settings", "Settings", "⚙️"),
        ]

        btn_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12)

        # Section label
        ctk.CTkLabel(
            btn_frame, text="  NAVIGATION",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=("gray55", "gray45"),
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        for key, label, icon in nav_items:
            btn = SidebarButton(
                btn_frame, text=label, icon=icon,
                command=lambda k=key: self._navigate(k),
            )
            btn.pack(fill="x", pady=1)
            self.nav_buttons[key] = btn

        # ── Tips section ──
        ctk.CTkFrame(self.sidebar, fg_color="transparent").pack(fill="both", expand=True)

        tips_frame = ctk.CTkFrame(
            self.sidebar,
            fg_color=("gray88", "gray15"),
            corner_radius=12,
        )
        tips_frame.pack(fill="x", padx=14, pady=(0, 8))

        ctk.CTkLabel(
            tips_frame, text="💡 Tip",
            font=ctk.CTkFont(size=11, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 2))

        ctk.CTkLabel(
            tips_frame,
            text="Run with sudo for full\nraw device access and\ndeep file scanning.",
            font=ctk.CTkFont(size=10),
            text_color=("gray45", "gray55"),
            anchor="w", justify="left",
        ).pack(fill="x", padx=12, pady=(0, 10))

        # ── Bottom status ──
        self.sidebar_status = ctk.CTkLabel(
            self.sidebar, text="v1.0  •  Ready",
            font=ctk.CTkFont(size=10),
            text_color=("gray50", "gray50"),
        )
        self.sidebar_status.pack(side="bottom", padx=18, pady=12)

        # ═══ Content area ═══
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        # ═══ Status bar ═══
        self.status_bar = ctk.CTkFrame(
            self, height=30,
            fg_color=("gray93", "gray11"),
            corner_radius=0,
        )
        self.status_bar.grid(row=1, column=1, sticky="ew")
        self.status_bar.grid_propagate(False)

        self.global_status = ctk.CTkLabel(
            self.status_bar,
            text="  🟢 Ready",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray55"),
            anchor="w",
        )
        self.global_status.pack(side="left", padx=8)

        self.global_progress = ctk.CTkProgressBar(
            self.status_bar, width=140, height=6,
            corner_radius=3,
            progress_color=("#2563eb", "#3b82f6"),
        )
        self.global_progress.pack(side="right", padx=12, pady=10)
        self.global_progress.set(0)

        # ═══ State ═══
        self._current_view: Optional[ctk.CTkFrame] = None
        self._current_page = ""

        self._navigate("dashboard")

    def _navigate(self, page: str, **kwargs):
        if self._current_view:
            self._current_view.destroy()
            self._current_view = None

        for key, btn in self.nav_buttons.items():
            btn.set_active(key == page)

        self._current_page = page

        if page == "dashboard":
            self._current_view = DashboardView(
                self.content,
                on_scan=self._go_to_scan,
                on_hex_view=self._go_to_hex,
                on_manage=self._go_to_manage,
                include_internal=self.settings.get("show_internal_drives", False),
            )
        elif page == "settings":
            self._current_view = SettingsView(
                self.content,
                on_settings_changed=self._on_settings_changed,
            )
        elif page == "scan":
            device = kwargs.get("device")
            if device:
                self._current_view = ScanView(
                    self.content, device=device,
                    on_recover=self._go_to_recovery,
                    on_back=lambda: self._navigate("dashboard"),
                )
        elif page == "recovery":
            device = kwargs.get("device")
            files = kwargs.get("files", [])
            if device:
                self._current_view = RecoveryView(
                    self.content, device=device, files=files,
                    on_back=lambda: self._navigate("dashboard"),
                )
        elif page == "hex":
            device = kwargs.get("device")
            if device:
                self._current_view = HexViewer(
                    self.content, device=device,
                    on_back=lambda: self._navigate("dashboard"),
                )
        elif page == "manage":
            device = kwargs.get("device")
            if device:
                self._current_view = DriveManageView(
                    self.content, device=device,
                    on_back=lambda: self._navigate("dashboard"),
                )

        if self._current_view:
            self._current_view.grid(row=0, column=0, sticky="nsew",
                                     padx=16, pady=16)

    def _go_to_scan(self, device: DeviceInfo):
        self._navigate("scan", device=device)
        self.global_status.configure(text=f"  🔍 Scanning {device.display_name}...")

    def _go_to_recovery(self, device: DeviceInfo, files: list[CarvedFile]):
        self._navigate("recovery", device=device, files=files)
        self.global_status.configure(
            text=f"  📥 Recovering {len(files)} files from {device.display_name}..."
        )

    def _go_to_hex(self, device: DeviceInfo):
        self._navigate("hex", device=device)
        self.global_status.configure(text=f"  🔢 Hex view: {device.display_name}")

    def _go_to_manage(self, device: DeviceInfo):
        self._navigate("manage", device=device)
        self.global_status.configure(text=f"  🛠️ Managing {device.display_name}")

    def _on_settings_changed(self, settings: dict):
        self.settings = settings
        self.global_status.configure(text="  ✅ Settings saved")
        if self._current_page == "dashboard" and isinstance(self._current_view, DashboardView):
            self._current_view.set_include_internal(
                settings.get("show_internal_drives", False)
            )
