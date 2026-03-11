"""
Device Scanner
Detects connected storage devices on macOS using diskutil + psutil.
"""

import json
import plistlib
import subprocess
from dataclasses import dataclass, field
from typing import Optional

import psutil


@dataclass
class DeviceInfo:
    """Information about a connected storage device."""
    identifier: str           # e.g. "disk4"
    name: str                 # e.g. "SANDISK"
    device_path: str          # e.g. "/dev/disk4"
    raw_device_path: str      # e.g. "/dev/rdisk4"
    size_bytes: int           # total size in bytes
    filesystem: str           # e.g. "FAT32", "NTFS", "APFS", "ExFAT"
    mount_point: Optional[str] = None  # e.g. "/Volumes/SANDISK"
    is_removable: bool = False
    is_internal: bool = False
    bus_protocol: str = ""    # e.g. "USB", "Thunderbolt"
    media_name: str = ""
    partitions: list = field(default_factory=list)

    @property
    def size_human(self) -> str:
        """Return human-readable size string."""
        size = self.size_bytes
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    @property
    def display_name(self) -> str:
        return self.name or self.media_name or self.identifier


@dataclass
class PartitionInfo:
    """Information about a partition on a device."""
    identifier: str
    name: str
    size_bytes: int
    filesystem: str
    mount_point: Optional[str] = None

    @property
    def size_human(self) -> str:
        size = self.size_bytes
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"


class DeviceScanner:
    """Scans for connected storage devices on macOS."""

    def __init__(self, include_internal: bool = False):
        self.include_internal = include_internal

    def scan(self) -> list[DeviceInfo]:
        """Discover all connected storage devices and return DeviceInfo list."""
        devices = []
        try:
            disk_list = self._get_diskutil_list()
            for disk_entry in disk_list:
                device = self._build_device_info(disk_entry)
                if device is None:
                    continue
                if not self.include_internal and device.is_internal:
                    continue
                devices.append(device)
        except Exception as e:
            print(f"[DeviceScanner] Error during scan: {e}")
        return devices

    def _get_diskutil_list(self) -> list[dict]:
        """Run `diskutil list -plist` and parse output."""
        try:
            result = subprocess.run(
                ["diskutil", "list", "-plist"],
                capture_output=True, timeout=15
            )
            plist = plistlib.loads(result.stdout)
            all_disks = plist.get("AllDisksAndPartitions", [])
            return all_disks
        except Exception as e:
            print(f"[DeviceScanner] diskutil list failed: {e}")
            return []

    def _get_disk_info(self, identifier: str) -> dict:
        """Run `diskutil info -plist <identifier>` and return dict."""
        try:
            result = subprocess.run(
                ["diskutil", "info", "-plist", identifier],
                capture_output=True, timeout=10
            )
            return plistlib.loads(result.stdout)
        except Exception:
            return {}

    def _build_device_info(self, disk_entry: dict) -> Optional[DeviceInfo]:
        """Build a DeviceInfo from a diskutil plist entry."""
        identifier = disk_entry.get("DeviceIdentifier", "")
        if not identifier:
            return None

        info = self._get_disk_info(identifier)
        if not info:
            return None

        # Determine if removable / internal
        is_internal = info.get("Internal", False)
        is_removable = info.get("Removable", False) or info.get("RemovableMedia", False)
        bus = info.get("BusProtocol", "")

        # USB drives are always external even if not marked removable
        if bus.upper() == "USB":
            is_removable = True
            is_internal = False

        size = info.get("TotalSize", info.get("Size", 0))
        fs = info.get("FilesystemType", info.get("FilesystemName", "Unknown"))
        mount = info.get("MountPoint", None)
        name = info.get("VolumeName", info.get("MediaName", identifier))

        # Build partition list
        partitions = []
        for part_entry in disk_entry.get("Partitions", []):
            part_id = part_entry.get("DeviceIdentifier", "")
            part_info = self._get_disk_info(part_id) if part_id else {}
            partitions.append(PartitionInfo(
                identifier=part_id,
                name=part_info.get("VolumeName", part_id),
                size_bytes=part_info.get("TotalSize", part_entry.get("Size", 0)),
                filesystem=part_info.get("FilesystemType",
                                         part_info.get("FilesystemName", "Unknown")),
                mount_point=part_info.get("MountPoint"),
            ))

        device = DeviceInfo(
            identifier=identifier,
            name=name,
            device_path=f"/dev/{identifier}",
            raw_device_path=f"/dev/r{identifier}",
            size_bytes=size,
            filesystem=fs,
            mount_point=mount,
            is_removable=is_removable,
            is_internal=is_internal,
            bus_protocol=bus,
            media_name=info.get("MediaName", ""),
            partitions=partitions,
        )
        return device


def quick_scan(include_internal: bool = False) -> list[DeviceInfo]:
    """Convenience function for a quick device scan."""
    return DeviceScanner(include_internal=include_internal).scan()
