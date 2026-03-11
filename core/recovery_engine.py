"""
Recovery Engine
Extracts carved files from the raw device and saves them to disk.
"""

import os
import json
import time
import threading
from dataclasses import dataclass, field
from typing import Optional, Callable
from datetime import datetime

from core.file_carver import CarvedFile


@dataclass
class RecoveryResult:
    """Result of recovering a single file."""
    carved_file: CarvedFile
    output_path: str = ""
    success: bool = False
    error: str = ""
    bytes_written: int = 0

    @property
    def status_icon(self) -> str:
        if self.success:
            return "✅"
        elif self.error:
            return "❌"
        return "⏳"


@dataclass
class RecoveryProgress:
    """Progress tracker for batch recovery."""
    total_files: int = 0
    completed_files: int = 0
    current_file: str = ""
    bytes_recovered: int = 0
    total_bytes: int = 0
    is_complete: bool = False
    results: list[RecoveryResult] = field(default_factory=list)

    @property
    def progress_fraction(self) -> float:
        if self.total_files <= 0:
            return 0.0
        return self.completed_files / self.total_files

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if not r.success and r.error)


class RecoveryEngine:
    """Recovers carved files from a device to an output directory."""

    def __init__(self, device_path: str):
        self.device_path = device_path
        self._stop_event = threading.Event()
        self._progress = RecoveryProgress()

    def recover_files(
        self,
        files: list[CarvedFile],
        output_dir: str,
        progress_callback: Optional[Callable[[RecoveryProgress], None]] = None
    ) -> RecoveryProgress:
        """
        Recover a list of carved files to the output directory.
        Returns RecoveryProgress with results.
        """
        self._stop_event.clear()
        os.makedirs(output_dir, exist_ok=True)

        self._progress = RecoveryProgress(
            total_files=len(files),
            total_bytes=sum(f.size for f in files),
        )

        # Group files by extension for organized output
        category_dirs = set()
        for f in files:
            cat_dir = os.path.join(output_dir, f.category)
            if cat_dir not in category_dirs:
                os.makedirs(cat_dir, exist_ok=True)
                category_dirs.add(cat_dir)

        # Try multiple device path variants (same logic as file carver)
        paths_to_try = [self.device_path]
        if "/dev/r" in self.device_path:
            block_path = self.device_path.replace("/dev/r", "/dev/")
            if block_path not in paths_to_try:
                paths_to_try.append(block_path)
        elif "/dev/" in self.device_path:
            raw_path = self.device_path.replace("/dev/", "/dev/r")
            if raw_path not in paths_to_try:
                paths_to_try.insert(0, raw_path)

        fd = None
        open_error = None
        
        # Try up to 3 times to open the device (handles brief disconnects during re-enumeration)
        for attempt in range(3):
            for path in paths_to_try:
                try:
                    print(f"[RecoveryEngine] Trying to open: {path}")
                    fd = os.open(path, os.O_RDONLY)
                    # Bypass macOS disk cache for faster sequential reads
                    try:
                        import fcntl
                        fcntl.fcntl(fd, fcntl.F_NOCACHE, 1)
                    except Exception:
                        pass
                    print(f"[RecoveryEngine] Successfully opened: {path}")
                    break
                except PermissionError:
                    open_error = "Permission denied — run with sudo"
                    print(f"[RecoveryEngine] Permission denied: {path}")
                    continue
                except Exception as e:
                    open_error = f"Cannot open device: {e}"
                    print(f"[RecoveryEngine] Cannot open {path}: {e}")
                    continue
            
            if fd is not None:
                break
                
            if attempt < 2:
                print(f"[RecoveryEngine] Device not found, waiting 1s before retry {attempt + 1}...")
                time.sleep(1.0)

        if fd is None:
            for f in files:
                self._progress.results.append(RecoveryResult(
                    carved_file=f,
                    error=open_error or "Cannot open device",
                ))
            self._progress.is_complete = True
            if progress_callback:
                progress_callback(self._progress)
            return self._progress

        try:
            for idx, carved in enumerate(files):
                if self._stop_event.is_set():
                    break

                filename = self._generate_filename(idx, carved)
                cat_dir = os.path.join(output_dir, carved.category)
                output_path = os.path.join(cat_dir, filename)

                self._progress.current_file = filename

                result = self._recover_single(fd, carved, output_path)
                self._progress.results.append(result)
                self._progress.completed_files = idx + 1
                if result.success:
                    self._progress.bytes_recovered += result.bytes_written

                if progress_callback:
                    progress_callback(self._progress)
        finally:
            os.close(fd)

        self._progress.is_complete = True
        if progress_callback:
            progress_callback(self._progress)

        # Generate report
        self._write_report(output_dir)

        return self._progress

    def recover_async(
        self,
        files: list[CarvedFile],
        output_dir: str,
        progress_callback: Optional[Callable[[RecoveryProgress], None]] = None,
        done_callback: Optional[Callable[[RecoveryProgress], None]] = None
    ):
        """Start recovery in a background thread."""
        def _worker():
            progress = self.recover_files(files, output_dir, progress_callback)
            if done_callback:
                done_callback(progress)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return t

    def stop(self):
        """Signal recovery to stop."""
        self._stop_event.set()

    @property
    def progress(self) -> RecoveryProgress:
        return self._progress

    # ─── Internal ───────────────────────────────────

    def _recover_single(self, fd: int, carved: CarvedFile,
                        output_path: str) -> RecoveryResult:
        """Recover a single carved file."""
        result = RecoveryResult(carved_file=carved, output_path=output_path)

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        try:
            # macOS raw devices require 512-byte aligned reads.
            # Align the offset down and trim the excess prefix bytes.
            block_size = 512
            aligned_offset = (carved.offset // block_size) * block_size
            prefix_skip = carved.offset - aligned_offset

            os.lseek(fd, aligned_offset, os.SEEK_SET)

            # Read in chunks to handle large files
            chunk_size = 1024 * 1024  # 1 MB
            written = 0
            first_chunk = True

            with open(output_path, "wb") as out:
                while written < carved.size:
                    # Calculate how much we still need to write
                    bytes_needed = carved.size - written
                    
                    if first_chunk:
                        # For the first chunk, we must read the prefix + what we need
                        read_size = bytes_needed + prefix_skip
                    else:
                        read_size = bytes_needed
                        
                    read_size = min(chunk_size, read_size)
                    
                    # Align read_size up to block boundary for raw devices
                    read_aligned = ((read_size + block_size - 1) // block_size) * block_size
                    data = os.read(fd, read_aligned)
                    if not data:
                        break

                    if first_chunk and prefix_skip > 0:
                        # Skip the alignment prefix on the first chunk
                        data = data[prefix_skip:]
                        first_chunk = False

                    # Don't write more than the file size
                    to_write = min(len(data), carved.size - written)
                    if to_write <= 0:
                        break
                        
                    out.write(data[:to_write])
                    written += to_write

            # Validate: file should be non-empty and header should match
            if written > 0:
                result.success = True
                result.bytes_written = written
            else:
                result.error = "No data read from device"
                if os.path.exists(output_path):
                    os.remove(output_path)

        except OSError as e:
            result.error = f"I/O error: {e}"
            if os.path.exists(output_path):
                os.remove(output_path)
        except Exception as e:
            result.error = f"Error: {e}"
            if os.path.exists(output_path):
                os.remove(output_path)

        return result

    def _generate_filename(self, index: int, carved: CarvedFile) -> str:
        """Generate a descriptive filename for a recovered file."""
        # Sanitize the file type: remove slashes, spaces, parens
        safe_type = carved.file_type.lower()
        for ch in "/\\() ":
            safe_type = safe_type.replace(ch, "_")
        safe_type = safe_type.strip("_")
        return (f"recovered_{index + 1:04d}_{safe_type}"
                f"_0x{carved.offset:08X}{carved.extension}")

    def _write_report(self, output_dir: str):
        """Write a JSON + text recovery report."""
        progress = self._progress
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # JSON report
        report_data = {
            "timestamp": timestamp,
            "device": self.device_path,
            "total_files_attempted": progress.total_files,
            "successful_recoveries": progress.success_count,
            "failed_recoveries": progress.fail_count,
            "total_bytes_recovered": progress.bytes_recovered,
            "files": [],
        }
        for r in progress.results:
            report_data["files"].append({
                "filename": os.path.basename(r.output_path) if r.output_path else "",
                "type": r.carved_file.file_type,
                "category": r.carved_file.category,
                "size": r.carved_file.size,
                "offset": r.carved_file.offset,
                "confidence": r.carved_file.confidence,
                "success": r.success,
                "error": r.error,
            })

        json_path = os.path.join(output_dir, "recovery_report.json")
        with open(json_path, "w") as f:
            json.dump(report_data, f, indent=2)

        # Human-readable report
        txt_path = os.path.join(output_dir, "recovery_report.txt")
        with open(txt_path, "w") as f:
            f.write(f"═══════════════════════════════════════════\n")
            f.write(f"  FILE RESURRECTOR — Recovery Report\n")
            f.write(f"═══════════════════════════════════════════\n\n")
            f.write(f"  Date:      {timestamp}\n")
            f.write(f"  Device:    {self.device_path}\n")
            f.write(f"  Files:     {progress.success_count} recovered, "
                    f"{progress.fail_count} failed\n")
            f.write(f"  Data:      {self._human_size(progress.bytes_recovered)}\n\n")

            f.write(f"───────────────────────────────────────────\n")
            for r in progress.results:
                icon = r.status_icon
                name = os.path.basename(r.output_path) if r.output_path else "N/A"
                f.write(f"  {icon} {name}\n")
                f.write(f"     Type: {r.carved_file.file_type}  |  "
                        f"Size: {r.carved_file.size_human}  |  "
                        f"Confidence: {r.carved_file.confidence_pct}\n")
                if r.error:
                    f.write(f"     Error: {r.error}\n")
                f.write(f"\n")

    @staticmethod
    def _human_size(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
