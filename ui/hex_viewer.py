"""
Hex Viewer
Classic hex editor view for inspecting raw device bytes.
"""

import os
import threading
import customtkinter as ctk
from typing import Optional, Callable

from core.device_scanner import DeviceInfo
from core.file_signatures import SIGNATURES


# Color palette for signature highlighting
SIG_COLORS = [
    "#3b82f6", "#ef4444", "#22c55e", "#f59e0b", "#8b5cf6",
    "#ec4899", "#06b6d4", "#f97316", "#14b8a6", "#a855f7",
]


class HexViewer(ctk.CTkFrame):
    """Raw hex + ASCII viewer for a device."""

    BYTES_PER_ROW = 16
    ROWS_PER_PAGE = 32

    def __init__(self, master, device: DeviceInfo,
                 on_back: Callable, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.device = device
        self.on_back = on_back
        self._fd: Optional[int] = None
        self._current_offset = 0
        self._page_size = self.BYTES_PER_ROW * self.ROWS_PER_PAGE  # 512 bytes

        # Determine device path
        self._device_path = device.raw_device_path
        for p in device.partitions:
            if p.mount_point:
                self._device_path = f"/dev/r{p.identifier}"
                break

        self._build_ui()
        self._load_page(0)

    def _build_ui(self):
        # ── Header ──
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 8))

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
            text=f"🔢 Hex Viewer: {self.device.display_name}",
            font=ctk.CTkFont(size=22, weight="bold"),
            anchor="w",
        ).pack(side="left", padx=12)

        # ── Navigation bar ──
        nav = ctk.CTkFrame(self, fg_color=("gray90", "gray17"),
                           corner_radius=12)
        nav.pack(fill="x", pady=(0, 8))

        nav_inner = ctk.CTkFrame(nav, fg_color="transparent")
        nav_inner.pack(fill="x", padx=12, pady=10)

        ctk.CTkLabel(
            nav_inner, text="Go to offset:",
            font=ctk.CTkFont(size=13),
        ).pack(side="left")

        self.offset_entry = ctk.CTkEntry(
            nav_inner, width=160,
            font=ctk.CTkFont(family="Menlo", size=13),
            height=32, corner_radius=8,
            placeholder_text="0x00000000",
        )
        self.offset_entry.pack(side="left", padx=8)
        self.offset_entry.bind("<Return>", lambda e: self._jump_to_offset())

        ctk.CTkButton(
            nav_inner, text="Go", width=60,
            font=ctk.CTkFont(size=12, weight="bold"),
            height=32, corner_radius=8,
            fg_color=("#2563eb", "#1d4ed8"),
            hover_color=("#1e40af", "#1e3a8a"),
            command=self._jump_to_offset,
        ).pack(side="left")

        # Page navigation
        self.prev_btn = ctk.CTkButton(
            nav_inner, text="◀ Prev", width=80,
            font=ctk.CTkFont(size=12),
            height=32, corner_radius=8,
            fg_color=("gray75", "gray30"),
            hover_color=("gray65", "gray40"),
            command=self._prev_page,
        )
        self.prev_btn.pack(side="right")

        self.next_btn = ctk.CTkButton(
            nav_inner, text="Next ▶", width=80,
            font=ctk.CTkFont(size=12),
            height=32, corner_radius=8,
            fg_color=("gray75", "gray30"),
            hover_color=("gray65", "gray40"),
            command=self._next_page,
        )
        self.next_btn.pack(side="right", padx=(0, 4))

        self.offset_label = ctk.CTkLabel(
            nav_inner, text="Offset: 0x00000000",
            font=ctk.CTkFont(family="Menlo", size=12),
            text_color=("gray50", "gray55"),
        )
        self.offset_label.pack(side="right", padx=12)

        # ── Loading indicator ──
        self.loading_bar = ctk.CTkProgressBar(
            self, height=4, corner_radius=2,
            progress_color=("#2563eb", "#3b82f6"),
            mode="indeterminate",
        )

        # ── Hex display ──
        self.hex_display = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Menlo", size=13),
            fg_color=("gray95", "gray10"),
            corner_radius=12,
            wrap="none",
        )
        self.hex_display.pack(fill="both", expand=True, pady=(0, 8))

        # ── Signature legend ──
        legend = ctk.CTkFrame(self, fg_color=("gray90", "gray17"),
                              corner_radius=10, height=50)
        legend.pack(fill="x")
        legend.pack_propagate(False)

        ctk.CTkLabel(
            legend, text="Known signatures highlighted •",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray55"),
        ).pack(side="left", padx=12)

        for i, sig in enumerate(SIGNATURES[:8]):
            color = SIG_COLORS[i % len(SIG_COLORS)]
            ctk.CTkLabel(
                legend, text=f"■ {sig.name}",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=color,
            ).pack(side="left", padx=4)

        # ── Status ──
        self.status_label = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray55"),
        )
        self.status_label.pack(fill="x", pady=(4, 0))

    def _load_page(self, offset: int):
        """Load and display a page of hex data from the device."""
        self._current_offset = max(0, offset)

        # Show loading
        self.loading_bar.pack(fill="x", pady=(0, 4), before=self.hex_display)
        self.loading_bar.start()
        self.status_label.configure(text="Reading device...")

        def _read():
            data = b""
            error = ""
            try:
                fd = os.open(self._device_path, os.O_RDONLY)
                try:
                    os.lseek(fd, self._current_offset, os.SEEK_SET)
                    data = os.read(fd, self._page_size)
                finally:
                    os.close(fd)
            except PermissionError:
                error = "Permission denied — try running with sudo"
            except Exception as e:
                error = str(e)
            self.after(0, lambda: self._render_hex(data, error))

        threading.Thread(target=_read, daemon=True).start()

    def _render_hex(self, data: bytes, error: str = ""):
        """Render hex data into the textbox."""
        self.loading_bar.stop()
        self.loading_bar.pack_forget()

        self.hex_display.configure(state="normal")
        self.hex_display.delete("1.0", "end")

        if error:
            self.hex_display.insert("end", f"\n  ⚠️  {error}\n")
            self.hex_display.configure(state="disabled")
            self.status_label.configure(text=error)
            return

        if not data:
            self.hex_display.insert("end", "\n  (No data at this offset)\n")
            self.hex_display.configure(state="disabled")
            return

        # Build header
        header = "  Offset    │ "
        header += " ".join(f"{i:02X}" for i in range(self.BYTES_PER_ROW))
        header += " │ ASCII\n"
        header += "  ──────────┼─" + "─" * (self.BYTES_PER_ROW * 3 - 1) + "─┼─" + "─" * self.BYTES_PER_ROW + "\n"
        self.hex_display.insert("end", header)

        # Detect signatures in this page
        sig_ranges = self._find_signatures_in_data(data)

        # Render rows
        for row_idx in range(0, len(data), self.BYTES_PER_ROW):
            row_data = data[row_idx:row_idx + self.BYTES_PER_ROW]
            abs_offset = self._current_offset + row_idx

            # Offset column
            line = f"  {abs_offset:08X}  │ "

            # Hex bytes
            hex_parts = []
            for i, byte in enumerate(row_data):
                hex_parts.append(f"{byte:02X}")
            # Pad if last row is short
            while len(hex_parts) < self.BYTES_PER_ROW:
                hex_parts.append("  ")
            line += " ".join(hex_parts)

            # ASCII column
            line += " │ "
            for byte in row_data:
                if 32 <= byte < 127:
                    line += chr(byte)
                else:
                    line += "."

            self.hex_display.insert("end", line + "\n")

        self.hex_display.configure(state="disabled")

        self.offset_label.configure(
            text=f"Offset: 0x{self._current_offset:08X}"
        )
        self.status_label.configure(
            text=f"Showing {len(data)} bytes from offset 0x{self._current_offset:08X}"
            + (f"  •  {len(sig_ranges)} signature(s) detected" if sig_ranges else "")
        )

    def _find_signatures_in_data(self, data: bytes) -> list[tuple[int, int, str]]:
        """Find any known file signatures in the current page data."""
        found = []
        for sig in SIGNATURES:
            if sig.header_offset > 0:
                continue
            pos = data.find(sig.header)
            while pos != -1:
                found.append((pos, pos + len(sig.header), sig.name))
                pos = data.find(sig.header, pos + 1)
        return found

    def _jump_to_offset(self):
        text = self.offset_entry.get().strip()
        try:
            if text.startswith("0x") or text.startswith("0X"):
                offset = int(text, 16)
            else:
                offset = int(text)
            self._load_page(offset)
        except ValueError:
            self.status_label.configure(text="Invalid offset — use decimal or 0x hex")

    def _prev_page(self):
        new_offset = max(0, self._current_offset - self._page_size)
        self._load_page(new_offset)

    def _next_page(self):
        self._load_page(self._current_offset + self._page_size)

    def destroy(self):
        super().destroy()
