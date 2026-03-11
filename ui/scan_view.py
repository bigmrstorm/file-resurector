"""
Scan View
UI for configuring and running file carving scans with real-time progress and file preview.
"""

import os
import io
import threading
import customtkinter as ctk
from typing import Callable, Optional

from core.device_scanner import DeviceInfo
from core.file_carver import FileCarver, ScanConfig, ScanProgress, CarvedFile
from core.file_signatures import get_all_categories
from core.file_preview import FilePreview

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class ScanView(ctk.CTkFrame):
    """View for scanning a device for recoverable files, with preview."""

    def __init__(self, master, device: DeviceInfo,
                 on_recover: Callable[[DeviceInfo, list[CarvedFile]], None],
                 on_back: Callable, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.device = device
        self.on_recover = on_recover
        self.on_back = on_back
        self._carver: Optional[FileCarver] = None
        self._results: list[CarvedFile] = []
        self._filtered_results: list[CarvedFile] = []
        self._preview_images: dict = {}  # Keep references to prevent GC

        # Determine device path
        self._device_path = self.device.raw_device_path
        for p in self.device.partitions:
            if p.mount_point:
                self._device_path = f"/dev/r{p.identifier}"
                break

        self._build_ui()

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
            text=f"🔍 Scan: {self.device.display_name}",
            font=ctk.CTkFont(size=22, weight="bold"),
            anchor="w",
        ).pack(side="left", padx=12)

        # ── Config panel ──
        config = ctk.CTkFrame(self, fg_color=("gray90", "gray17"),
                              corner_radius=14)
        config.pack(fill="x", pady=(0, 10))

        # Depth
        depth_frame = ctk.CTkFrame(config, fg_color="transparent")
        depth_frame.pack(fill="x", padx=16, pady=(12, 6))

        ctk.CTkLabel(
            depth_frame, text="Scan Depth:",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="left")

        self.depth_var = ctk.StringVar(value="standard")
        for val, label, desc in [
            ("quick", "⚡ Quick", "~10%"),
            ("standard", "📊 Standard", "~50%"),
            ("deep", "🔬 Deep", "100%"),
        ]:
            ctk.CTkRadioButton(
                depth_frame, text=f"{label} ({desc})",
                variable=self.depth_var, value=val,
                font=ctk.CTkFont(size=12),
            ).pack(side="left", padx=(16, 4))

        # Categories
        cat_frame = ctk.CTkFrame(config, fg_color="transparent")
        cat_frame.pack(fill="x", padx=16, pady=(2, 12))

        ctk.CTkLabel(
            cat_frame, text="File Types:",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="left")

        self.category_vars: dict[str, ctk.BooleanVar] = {}
        icons = {
            "Image": "🖼️", "Document": "📄", "Audio": "🎵",
            "Video": "🎬", "Archive": "📦", "Database": "🗄️",
            "Executable": "⚙️", "Other": "📎",
        }
        for cat in get_all_categories():
            var = ctk.BooleanVar(value=True)
            self.category_vars[cat] = var
            ctk.CTkCheckBox(
                cat_frame, text=f"{icons.get(cat, '📁')} {cat}",
                variable=var, font=ctk.CTkFont(size=11),
                checkbox_width=16, checkbox_height=16,
            ).pack(side="left", padx=(12, 0))

        # ── Start/Stop buttons ──
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 8))

        self.start_btn = ctk.CTkButton(
            btn_row, text="▶  Start Scan",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=42, corner_radius=12,
            fg_color=("#2563eb", "#1d4ed8"),
            hover_color=("#1e40af", "#1e3a8a"),
            command=self._start_scan,
        )
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 4))

        self.stop_btn = ctk.CTkButton(
            btn_row, text="⏹ Stop", width=100,
            font=ctk.CTkFont(size=14, weight="bold"),
            height=42, corner_radius=12,
            fg_color=("#dc2626", "#b91c1c"),
            hover_color=("#b91c1c", "#991b1b"),
            state="disabled",
            command=self._stop_scan,
        )
        self.stop_btn.pack(side="left", padx=(4, 0))

        # ── Progress area ──
        progress_card = ctk.CTkFrame(self, fg_color=("gray90", "gray17"),
                                     corner_radius=14)
        progress_card.pack(fill="x", pady=(0, 10))

        self.progress_bar = ctk.CTkProgressBar(
            progress_card, height=16, corner_radius=8,
            progress_color=("#2563eb", "#3b82f6"),
        )
        self.progress_bar.pack(fill="x", padx=16, pady=(14, 6))
        self.progress_bar.set(0)

        stats_frame = ctk.CTkFrame(progress_card, fg_color="transparent")
        stats_frame.pack(fill="x", padx=16, pady=(0, 12))

        self.progress_label = ctk.CTkLabel(
            stats_frame, text="Ready to scan",
            font=ctk.CTkFont(size=13), anchor="w",
        )
        self.progress_label.pack(side="left")

        self.eta_label = ctk.CTkLabel(
            stats_frame, text="",
            font=ctk.CTkFont(size=12),
            text_color=("gray50", "gray55"), anchor="e",
        )
        self.eta_label.pack(side="right")

        self.speed_label = ctk.CTkLabel(
            stats_frame, text="",
            font=ctk.CTkFont(size=12),
            text_color=("gray50", "gray55"), anchor="e",
        )
        self.speed_label.pack(side="right", padx=(0, 14))

        # ── Content pane: results + preview ──
        content_pane = ctk.CTkFrame(self, fg_color="transparent")
        content_pane.pack(fill="both", expand=True)
        content_pane.grid_columnconfigure(0, weight=3)
        content_pane.grid_columnconfigure(1, weight=1)
        content_pane.grid_rowconfigure(0, weight=1)

        # ── Results list (left) ──
        left = ctk.CTkFrame(content_pane, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        results_header = ctk.CTkFrame(left, fg_color="transparent")
        results_header.pack(fill="x", pady=(0, 4))

        self.results_title = ctk.CTkLabel(
            results_header, text="Found Files (0)",
            font=ctk.CTkFont(size=15, weight="bold"), anchor="w",
        )
        self.results_title.pack(side="left")

        ctk.CTkOptionMenu(
            results_header,
            values=["Sort: Offset", "Sort: Size ↑", "Sort: Size ↓",
                    "Sort: Confidence", "Sort: Type"],
            font=ctk.CTkFont(size=11), width=130, height=28,
            command=self._on_sort_changed,
        ).pack(side="right")

        self.recover_btn = ctk.CTkButton(
            results_header, text="📥 Recover Selected",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=28, corner_radius=8,
            fg_color=("#059669", "#047857"),
            hover_color=("#047857", "#065f46"),
            state="disabled",
            command=self._recover_selected,
        )
        self.recover_btn.pack(side="right", padx=(0, 6))

        self.select_all_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            results_header, text="All",
            variable=self.select_all_var,
            font=ctk.CTkFont(size=11),
            command=self._toggle_select_all,
            checkbox_width=16, checkbox_height=16,
        ).pack(side="right", padx=(0, 6))

        self.results_frame = ctk.CTkScrollableFrame(
            left, fg_color=("gray92", "gray14"), corner_radius=12,
        )
        self.results_frame.pack(fill="both", expand=True)

        # ── Preview panel (right) ──
        self.preview_panel = ctk.CTkFrame(
            content_pane,
            fg_color=("gray90", "gray17"),
            corner_radius=14,
        )
        self.preview_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        ctk.CTkLabel(
            self.preview_panel, text="📷 Preview",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(padx=12, pady=(12, 6))

        self.preview_label = ctk.CTkLabel(
            self.preview_panel, text="Select a file\nto preview",
            font=ctk.CTkFont(size=12),
            text_color=("gray50", "gray55"),
            justify="center",
        )
        self.preview_label.pack(padx=12, pady=8)

        self.preview_image_label = ctk.CTkLabel(
            self.preview_panel, text="",
        )

        self.preview_text = ctk.CTkTextbox(
            self.preview_panel, height=200,
            font=ctk.CTkFont(family="Menlo", size=10),
            fg_color=("gray95", "gray10"),
            corner_radius=8, state="disabled",
        )

        self.preview_info = ctk.CTkLabel(
            self.preview_panel, text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray55"),
            justify="left", anchor="w",
        )
        self.preview_info.pack(padx=12, pady=(4, 12), fill="x")

        self._result_widgets: list = []
        self._result_check_vars: dict[int, ctk.BooleanVar] = {}

    def _start_scan(self):
        depth = self.depth_var.get()
        selected_cats = [c for c, v in self.category_vars.items() if v.get()]
        if not selected_cats:
            selected_cats = None

        config = ScanConfig(depth=depth, categories=selected_cats)

        # Determine the best device path and size for scanning.
        # For corrupted/unmounted drives, use the whole raw disk.
        # For mounted drives, prefer the partition's raw device.
        device_path = self.device.raw_device_path  # e.g. /dev/rdisk4
        size = self.device.size_bytes

        # If a partition is mounted, we can scan just that partition
        for p in self.device.partitions:
            if p.mount_point:
                device_path = f"/dev/r{p.identifier}"
                size = p.size_bytes
                break

        # Safety: if size is 0 or missing, use the whole disk size
        if size <= 0:
            size = self.device.size_bytes

        # Safety: also try the non-raw path as fallback
        self._scan_device_path = device_path
        self._scan_fallback_path = self.device.device_path  # e.g. /dev/disk4

        print(f"[ScanView] Scanning device_path={device_path}, size={size}")

        self._carver = FileCarver(device_path, size, config)

        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.recover_btn.configure(state="disabled")
        self.progress_bar.set(0)
        self._clear_results()
        self.progress_label.configure(text="Starting scan...")

        self._carver.scan_async(
            progress_callback=lambda p: self.after(0, lambda p=p: self._update_progress(p)),
            done_callback=lambda r: self.after(0, lambda r=r: self._scan_complete(r)),
        )

    def _stop_scan(self):
        if self._carver:
            self._carver.stop()
        self.stop_btn.configure(state="disabled")

    def _update_progress(self, progress: ScanProgress):
        if not self.winfo_exists() or not self.progress_bar.winfo_exists():
            return
            
        self.progress_bar.set(progress.progress_fraction)

        # Show errors prominently in the progress label
        if progress.error:
            self.progress_label.configure(
                text=f"⚠️ {progress.error}",
                text_color=("#dc2626", "#f87171"),
            )
            return

        self.progress_label.configure(
            text=f"{progress.progress_pct}  •  {progress.files_found} files found",
            text_color=("gray20", "gray80"),
        )
        self.speed_label.configure(text=progress.speed_human)
        self.eta_label.configure(text=f"ETA: {progress.eta_human}")

    def _scan_complete(self, results: list[CarvedFile]):
        if not self.winfo_exists():
            return
            
        self._results = results
        self._filtered_results = list(results)
        
        if not getattr(self, "start_btn", None) or not self.start_btn.winfo_exists():
            return
            
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        if results:
            self.recover_btn.configure(state="normal")

        # Check if the carver reported an error (e.g. permission denied)
        if self._carver and self._carver.progress.error:
            error_msg = self._carver.progress.error
            self.progress_label.configure(
                text=f"❌ {error_msg}",
                text_color=("#dc2626", "#f87171"),
            )
            self.progress_bar.configure(progress_color=("#dc2626", "#ef4444"))
            self.progress_bar.set(1.0)
        else:
            self.progress_label.configure(
                text=f"✅ Complete — {len(results)} files found",
                text_color=("gray20", "gray80"),
            )
            self.progress_bar.set(1.0)
        self._display_results()

    def _clear_results(self):
        for w in self._result_widgets:
            w.destroy()
        self._result_widgets.clear()
        self._result_check_vars.clear()
        self.results_title.configure(text="Found Files (0)")

    def _display_results(self):
        self._clear_results()
        self.results_title.configure(
            text=f"Found Files ({len(self._filtered_results)})"
        )

        icons = {
            "Image": "🖼️", "Document": "📄", "Audio": "🎵",
            "Video": "🎬", "Archive": "📦", "Database": "🗄️",
            "Executable": "⚙️", "Other": "📎",
        }

        # Table header
        hdr = ctk.CTkFrame(self.results_frame, fg_color=("gray85", "gray22"),
                           corner_radius=6, height=28)
        hdr.pack(fill="x", pady=(0, 3))
        hdr.pack_propagate(False)
        for text, w in [("", 34), ("Type", 130), ("Cat", 70),
                        ("Size", 80), ("Conf", 60), ("Offset", 100)]:
            ctk.CTkLabel(
                hdr, text=text, width=w,
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=("gray40", "gray60"), anchor="w",
            ).pack(side="left", padx=3)
        self._result_widgets.append(hdr)

        for idx, f in enumerate(self._filtered_results[:500]):
            var = ctk.BooleanVar(value=True)
            self._result_check_vars[idx] = var

            bg = ("gray95", "gray16") if idx % 2 == 0 else ("gray91", "gray19")
            row = ctk.CTkFrame(self.results_frame, fg_color=bg,
                               corner_radius=5, height=28)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            # Make row clickable for preview
            row.bind("<Button-1>", lambda e, i=idx: self._show_preview(i))

            ctk.CTkCheckBox(
                row, text="", variable=var,
                width=26, checkbox_width=14, checkbox_height=14,
            ).pack(side="left", padx=(6, 0))

            icon = icons.get(f.category, "📁")
            type_lbl = ctk.CTkLabel(
                row, text=f"{icon} {f.file_type}", width=130,
                font=ctk.CTkFont(size=11), anchor="w",
            )
            type_lbl.pack(side="left", padx=3)
            type_lbl.bind("<Button-1>", lambda e, i=idx: self._show_preview(i))

            ctk.CTkLabel(
                row, text=f.category, width=70,
                font=ctk.CTkFont(size=11), anchor="w",
            ).pack(side="left", padx=3)

            ctk.CTkLabel(
                row, text=f.size_human, width=80,
                font=ctk.CTkFont(size=11), anchor="w",
            ).pack(side="left", padx=3)

            conf_color = "#22c55e" if f.confidence >= 0.7 else (
                "#f59e0b" if f.confidence >= 0.4 else "#ef4444")
            ctk.CTkLabel(
                row, text=f.confidence_pct, width=60,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=conf_color, anchor="w",
            ).pack(side="left", padx=3)

            ctk.CTkLabel(
                row, text=f"0x{f.offset:08X}", width=100,
                font=ctk.CTkFont(family="Menlo", size=10), anchor="w",
            ).pack(side="left", padx=3)

            self._result_widgets.append(row)

    def _show_preview(self, idx: int):
        """Show a preview of the selected file in the preview panel."""
        if idx >= len(self._filtered_results):
            return

        f = self._filtered_results[idx]

        # Update info
        self.preview_info.configure(
            text=(f"Type: {f.file_type}\n"
                  f"Size: {f.size_human}\n"
                  f"Offset: 0x{f.offset:08X}\n"
                  f"Confidence: {f.confidence_pct}")
        )

        # Hide previous preview widgets
        self.preview_image_label.pack_forget()
        self.preview_text.pack_forget()

        preview_type = FilePreview.get_preview_type(f.extension)

        # Load preview in background
        self.preview_label.configure(text="Loading preview...")

        def _load():
            raw_data = FilePreview.read_raw_preview_data(
                self._device_path, f.offset, f.size, max_read=65536
            )
            self.after(0, lambda: self._render_preview(f, preview_type, raw_data))

        threading.Thread(target=_load, daemon=True).start()

    def _render_preview(self, f: CarvedFile, preview_type: str, raw_data: bytes):
        """Render the preview in the panel."""
        if not self.winfo_exists():
            return
            
        try:
            self.preview_image_label.pack_forget()
            self.preview_text.pack_forget()
        except Exception:
            pass

        if not getattr(self, "preview_label", None) or not self.preview_label.winfo_exists():
            return

        if not raw_data:
            self.preview_label.configure(text="No data available\n(need sudo?)")
            return

        if preview_type == "image" and HAS_PIL:
            try:
                img = FilePreview.generate_image_thumbnail(raw_data=raw_data, size=(200, 200))
                if img:
                    ctk_img = ctk.CTkImage(light_image=img, dark_image=img,
                                           size=(min(img.width, 200), min(img.height, 200)))
                    self._preview_images[f.offset] = ctk_img
                    self.preview_image_label.configure(image=ctk_img, text="")
                    self.preview_image_label.pack(padx=12, pady=4)
                    self.preview_label.configure(text="🖼️ Image Preview")
                    return
            except Exception:
                pass

        if preview_type == "text":
            text = FilePreview.generate_text_preview(raw_data=raw_data, max_bytes=2048)
            self.preview_text.configure(state="normal")
            self.preview_text.delete("1.0", "end")
            self.preview_text.insert("end", text)
            self.preview_text.configure(state="disabled")
            self.preview_text.pack(fill="both", expand=True, padx=12, pady=4)
            self.preview_label.configure(text="📄 Text Preview")
            return

        # Hex fallback
        hex_text = FilePreview.generate_hex_preview(raw_data=raw_data, max_bytes=256)
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("end", hex_text)
        self.preview_text.configure(state="disabled")
        self.preview_text.pack(fill="both", expand=True, padx=12, pady=4)
        self.preview_label.configure(text="🔢 Hex Preview")

    def _on_sort_changed(self, choice: str):
        if not self._filtered_results:
            return
        if "Size ↑" in choice:
            self._filtered_results.sort(key=lambda f: f.size)
        elif "Size ↓" in choice:
            self._filtered_results.sort(key=lambda f: f.size, reverse=True)
        elif "Confidence" in choice:
            self._filtered_results.sort(key=lambda f: f.confidence, reverse=True)
        elif "Type" in choice:
            self._filtered_results.sort(key=lambda f: f.file_type)
        else:
            self._filtered_results.sort(key=lambda f: f.offset)
        self._display_results()

    def _toggle_select_all(self):
        val = self.select_all_var.get()
        for var in self._result_check_vars.values():
            var.set(val)

    def _recover_selected(self):
        selected = []
        for idx, var in self._result_check_vars.items():
            if var.get() and idx < len(self._filtered_results):
                selected.append(self._filtered_results[idx])
        if selected:
            self.on_recover(self.device, selected)
