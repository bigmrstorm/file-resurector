"""
Drive Manager
Provides drive management operations: format, erase, rename, mount/unmount, partition info.
All operations use macOS diskutil commands.
"""

import os
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Optional, Callable
from enum import Enum


class FilesystemType(Enum):
    APFS = "APFS"
    HFS_PLUS = "HFS+"
    FAT32 = "FAT32"
    EXFAT = "ExFAT"
    NTFS = "NTFS"  # Read-only on macOS by default

    @property
    def diskutil_name(self) -> str:
        mapping = {
            "APFS": "APFS",
            "HFS+": "JHFS+",
            "FAT32": "FAT32",
            "ExFAT": "ExFAT",
        }
        return mapping.get(self.value, self.value)


@dataclass
class OperationResult:
    """Result of a drive management operation."""
    success: bool = False
    message: str = ""
    raw_output: str = ""
    error: str = ""

    @property
    def status_icon(self) -> str:
        return "✅" if self.success else "❌"


@dataclass
class DiskUsageInfo:
    """Detailed disk usage breakdown."""
    total_bytes: int = 0
    used_bytes: int = 0
    free_bytes: int = 0
    percent_used: float = 0.0

    @property
    def total_human(self) -> str:
        return _human_size(self.total_bytes)

    @property
    def used_human(self) -> str:
        return _human_size(self.used_bytes)

    @property
    def free_human(self) -> str:
        return _human_size(self.free_bytes)


def _human_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


class DriveManager:
    """Manages drive operations via macOS diskutil."""

    @staticmethod
    def erase_disk(identifier: str, filesystem: FilesystemType,
                   name: str = "Untitled",
                   progress_callback: Optional[Callable[[str], None]] = None
                   ) -> OperationResult:
        """
        Erase (format) an entire disk.
        ⚠️ THIS DESTROYS ALL DATA ON THE DISK.
        """
        result = OperationResult()

        if progress_callback:
            progress_callback(f"Erasing {identifier} as {filesystem.value}...")

        try:
            proc = subprocess.run(
                ["diskutil", "eraseDisk", filesystem.diskutil_name,
                 name, identifier],
                capture_output=True, text=True, timeout=300,
            )
            result.raw_output = proc.stdout + proc.stderr

            if proc.returncode == 0:
                result.success = True
                result.message = (f"Successfully erased {identifier} "
                                  f"as {filesystem.value} ({name})")
            else:
                result.error = proc.stderr.strip() or "Erase failed"
                result.message = f"Failed to erase {identifier}"

        except subprocess.TimeoutExpired:
            result.error = "Operation timed out (300s)"
        except Exception as e:
            result.error = str(e)

        if progress_callback:
            progress_callback(result.message)

        return result

    @staticmethod
    def erase_volume(identifier: str, filesystem: FilesystemType,
                     name: str = "Untitled") -> OperationResult:
        """Erase a single volume/partition."""
        result = OperationResult()
        try:
            proc = subprocess.run(
                ["diskutil", "eraseVolume", filesystem.diskutil_name,
                 name, identifier],
                capture_output=True, text=True, timeout=300,
            )
            result.raw_output = proc.stdout + proc.stderr
            if proc.returncode == 0:
                result.success = True
                result.message = f"Volume {identifier} erased as {filesystem.value}"
            else:
                result.error = proc.stderr.strip() or "Erase volume failed"
        except Exception as e:
            result.error = str(e)
        return result

    @staticmethod
    def rename_volume(identifier: str, new_name: str) -> OperationResult:
        """Rename a mounted volume."""
        result = OperationResult()
        try:
            proc = subprocess.run(
                ["diskutil", "rename", identifier, new_name],
                capture_output=True, text=True, timeout=30,
            )
            result.raw_output = proc.stdout + proc.stderr
            if proc.returncode == 0:
                result.success = True
                result.message = f"Renamed {identifier} to '{new_name}'"
            else:
                result.error = proc.stderr.strip() or "Rename failed"
        except Exception as e:
            result.error = str(e)
        return result

    @staticmethod
    def mount_volume(identifier: str) -> OperationResult:
        """Mount a volume."""
        result = OperationResult()
        try:
            proc = subprocess.run(
                ["diskutil", "mount", identifier],
                capture_output=True, text=True, timeout=30,
            )
            result.raw_output = proc.stdout + proc.stderr
            if proc.returncode == 0:
                result.success = True
                result.message = f"Mounted {identifier}"
            else:
                result.error = proc.stderr.strip() or "Mount failed"
        except Exception as e:
            result.error = str(e)
        return result

    @staticmethod
    def unmount_volume(identifier: str) -> OperationResult:
        """Unmount a volume."""
        result = OperationResult()
        try:
            proc = subprocess.run(
                ["diskutil", "unmount", identifier],
                capture_output=True, text=True, timeout=30,
            )
            result.raw_output = proc.stdout + proc.stderr
            if proc.returncode == 0:
                result.success = True
                result.message = f"Unmounted {identifier}"
            else:
                result.error = proc.stderr.strip() or "Unmount failed"
        except Exception as e:
            result.error = str(e)
        return result

    @staticmethod
    def eject_disk(identifier: str) -> OperationResult:
        """Eject an entire disk."""
        result = OperationResult()
        try:
            proc = subprocess.run(
                ["diskutil", "eject", identifier],
                capture_output=True, text=True, timeout=30,
            )
            result.raw_output = proc.stdout + proc.stderr
            if proc.returncode == 0:
                result.success = True
                result.message = f"Ejected {identifier}"
            else:
                result.error = proc.stderr.strip() or "Eject failed"
        except Exception as e:
            result.error = str(e)
        return result

    @staticmethod
    def get_disk_usage(mount_point: str) -> Optional[DiskUsageInfo]:
        """Get disk usage for a mounted volume."""
        if not mount_point or not os.path.ismount(mount_point):
            return None
        try:
            stat = os.statvfs(mount_point)
            total = stat.f_blocks * stat.f_frsize
            free = stat.f_bavail * stat.f_frsize
            used = total - free
            return DiskUsageInfo(
                total_bytes=total,
                used_bytes=used,
                free_bytes=free,
                percent_used=(used / total * 100) if total > 0 else 0,
            )
        except Exception:
            return None

    @staticmethod
    def get_disk_info_detailed(identifier: str) -> dict:
        """Get full diskutil info as a dictionary."""
        try:
            import plistlib
            proc = subprocess.run(
                ["diskutil", "info", "-plist", identifier],
                capture_output=True, timeout=10,
            )
            return plistlib.loads(proc.stdout)
        except Exception:
            return {}

    @staticmethod
    def repair_volume(identifier: str,
                      progress_callback: Optional[Callable[[str], None]] = None
                      ) -> OperationResult:
        """Attempt to repair a volume's filesystem."""
        result = OperationResult()
        if progress_callback:
            progress_callback(f"Repairing {identifier}...")

        try:
            proc = subprocess.run(
                ["diskutil", "repairVolume", identifier],
                capture_output=True, text=True, timeout=600,
            )
            result.raw_output = proc.stdout + proc.stderr

            if proc.returncode == 0:
                result.success = True
                result.message = f"Repair of {identifier} completed successfully"
            else:
                result.error = proc.stderr.strip() or "Repair failed"
                result.message = f"Repair of {identifier} failed"

        except subprocess.TimeoutExpired:
            result.error = "Repair timed out (600s)"
        except Exception as e:
            result.error = str(e)

        return result

    @staticmethod
    def get_smart_status(identifier: str) -> Optional[str]:
        """Get S.M.A.R.T. status for a disk (if supported)."""
        try:
            info = DriveManager.get_disk_info_detailed(identifier)
            return info.get("SMARTStatus", "Not Available")
        except Exception:
            return "Not Available"

    @staticmethod
    def run_async(func, *args, done_callback=None, **kwargs):
        """Run any operation in a background thread."""
        def _worker():
            result = func(*args, **kwargs)
            if done_callback:
                done_callback(result)
        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return t
