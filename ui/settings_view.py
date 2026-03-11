"""
Settings View
Application settings panel.
"""

import os
import json
import customtkinter as ctk
from typing import Callable, Optional


SETTINGS_PATH = os.path.expanduser("~/.file_resurrector_settings.json")

DEFAULT_SETTINGS = {
    "theme": "dark",
    "output_dir": os.path.expanduser("~/Desktop/Recovered Files"),
    "chunk_size_kb": 64,
    "show_internal_drives": False,
    "log_verbosity": "normal",
    "scan_depth": "standard",
}


def load_settings() -> dict:
    """Load settings from disk or return defaults."""
    try:
        with open(SETTINGS_PATH, "r") as f:
            saved = json.load(f)
        merged = {**DEFAULT_SETTINGS, **saved}
        return merged
    except Exception:
        return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict):
    """Save settings to disk."""
    try:
        with open(SETTINGS_PATH, "w") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"Failed to save settings: {e}")


class SettingsView(ctk.CTkScrollableFrame):
    """Settings panel for the application."""

    def __init__(self, master, on_settings_changed: Optional[Callable] = None,
                 **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.on_settings_changed = on_settings_changed
        self.settings = load_settings()

        self._build_ui()

    def _build_ui(self):
        # Title
        ctk.CTkLabel(
            self, text="⚙️ Settings",
            font=ctk.CTkFont(size=24, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 16))

        # ═══ Appearance ═══
        self._section_header("🎨  Appearance")

        theme_frame = self._setting_row("Theme")
        self.theme_var = ctk.StringVar(value=self.settings.get("theme", "dark"))
        theme_menu = ctk.CTkSegmentedButton(
            theme_frame,
            values=["Dark", "Light", "System"],
            font=ctk.CTkFont(size=12),
            command=self._on_theme_change,
        )
        theme_menu.set(self.settings.get("theme", "dark").capitalize())
        theme_menu.pack(side="right")

        # ═══ Scanning ═══
        self._section_header("🔍  Scanning")

        depth_frame = self._setting_row("Default Scan Depth")
        self.depth_var = ctk.StringVar(
            value=self.settings.get("scan_depth", "standard"))
        ctk.CTkSegmentedButton(
            depth_frame,
            values=["Quick", "Standard", "Deep"],
            font=ctk.CTkFont(size=12),
            command=self._on_depth_change,
        ).set(self.settings.get("scan_depth", "standard").capitalize())

        chunk_frame = self._setting_row("Chunk Size (KB)")
        self.chunk_var = ctk.StringVar(
            value=str(self.settings.get("chunk_size_kb", 64)))
        ctk.CTkOptionMenu(
            chunk_frame,
            values=["16", "32", "64", "128", "256", "512"],
            variable=self.chunk_var,
            font=ctk.CTkFont(size=12),
            width=100,
            command=self._on_setting_change,
        ).pack(side="right")

        internal_frame = self._setting_row("Show Internal Drives")
        self.internal_var = ctk.BooleanVar(
            value=self.settings.get("show_internal_drives", False))
        ctk.CTkSwitch(
            internal_frame, text="",
            variable=self.internal_var,
            command=self._on_setting_change,
        ).pack(side="right")

        # ═══ Recovery ═══
        self._section_header("📥  Recovery")

        dir_frame = self._setting_row("Default Output Directory")
        self.dir_entry = ctk.CTkEntry(
            dir_frame,
            font=ctk.CTkFont(size=12),
            height=32, corner_radius=8,
            width=300,
        )
        self.dir_entry.insert(0, self.settings.get(
            "output_dir", DEFAULT_SETTINGS["output_dir"]))
        self.dir_entry.pack(side="right")

        # ═══ Logging ═══
        self._section_header("📋  Logging")

        log_frame = self._setting_row("Log Verbosity")
        self.log_var = ctk.StringVar(
            value=self.settings.get("log_verbosity", "normal"))
        ctk.CTkSegmentedButton(
            log_frame,
            values=["Quiet", "Normal", "Verbose"],
            font=ctk.CTkFont(size=12),
            command=self._on_log_change,
        ).set(self.settings.get("log_verbosity", "normal").capitalize())

        # ═══ Save button ═══
        ctk.CTkFrame(self, height=20, fg_color="transparent").pack()

        self.save_btn = ctk.CTkButton(
            self, text="💾  Save Settings",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44, corner_radius=12,
            fg_color=("#059669", "#047857"),
            hover_color=("#047857", "#065f46"),
            command=self._save,
        )
        self.save_btn.pack(fill="x")

        self.save_status = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=12),
            text_color=("#22c55e", "#4ade80"),
        )
        self.save_status.pack(pady=(6, 0))

        # ═══ About ═══
        ctk.CTkFrame(self, height=20, fg_color="transparent").pack()
        self._section_header("ℹ️  About")

        about = ctk.CTkFrame(self, fg_color=("gray90", "gray17"),
                             corner_radius=12)
        about.pack(fill="x")

        about_text = (
            "File Resurrector v1.0\n\n"
            "A free, open-source file recovery tool.\n"
            "Scans corrupted drives for recoverable files using\n"
            "header-footer signature carving.\n\n"
            "⚠️  Always work on a disk image when possible.\n"
            "This tool performs read-only operations on the source drive."
        )
        ctk.CTkLabel(
            about, text=about_text,
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60"),
            justify="left", anchor="w",
        ).pack(padx=16, pady=16, fill="x")

    def _section_header(self, text: str):
        ctk.CTkFrame(self, height=8, fg_color="transparent").pack()
        ctk.CTkLabel(
            self, text=text,
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(8, 6))
        ctk.CTkFrame(
            self, height=1,
            fg_color=("gray80", "gray30"),
        ).pack(fill="x", pady=(0, 8))

    def _setting_row(self, label: str) -> ctk.CTkFrame:
        row = ctk.CTkFrame(self, fg_color=("gray90", "gray17"),
                           corner_radius=10, height=50)
        row.pack(fill="x", pady=3)
        row.pack_propagate(False)
        ctk.CTkLabel(
            row, text=label,
            font=ctk.CTkFont(size=13),
            anchor="w",
        ).pack(side="left", padx=16)
        return row

    def _on_theme_change(self, value: str):
        self.settings["theme"] = value.lower()
        ctk.set_appearance_mode(value.lower())

    def _on_depth_change(self, value: str):
        self.settings["scan_depth"] = value.lower()

    def _on_log_change(self, value: str):
        self.settings["log_verbosity"] = value.lower()

    def _on_setting_change(self, *args):
        pass  # Will be saved on explicit save

    def _save(self):
        self.settings["chunk_size_kb"] = int(self.chunk_var.get())
        self.settings["show_internal_drives"] = self.internal_var.get()
        self.settings["output_dir"] = self.dir_entry.get().strip()

        save_settings(self.settings)

        self.save_status.configure(text="✅ Settings saved!")
        self.after(3000, lambda: self.save_status.configure(text=""))

        if self.on_settings_changed:
            self.on_settings_changed(self.settings)

    def get_settings(self) -> dict:
        return self.settings
