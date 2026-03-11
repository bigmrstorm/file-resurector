"""
Corruption Detector
Checks filesystem health of a device using diskutil + direct I/O probing.
"""

import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class HealthStatus(Enum):
    HEALTHY = "Healthy"
    WARNING = "Warning"
    CORRUPTED = "Corrupted"
    UNKNOWN = "Unknown"


@dataclass
class HealthReport:
    """Report on a device's filesystem health."""
    device_identifier: str
    status: HealthStatus = HealthStatus.UNKNOWN
    summary: str = ""
    details: list[str] = field(default_factory=list)
    raw_output: str = ""
    readable_sectors: int = 0
    failed_sectors: int = 0
    total_probed: int = 0

    @property
    def status_emoji(self) -> str:
        return {
            HealthStatus.HEALTHY: "🟢",
            HealthStatus.WARNING: "🟡",
            HealthStatus.CORRUPTED: "🔴",
            HealthStatus.UNKNOWN: "⚪",
        }.get(self.status, "⚪")


class CorruptionDetector:
    """Detects corruption on a storage device."""

    def __init__(self, device_identifier: str, device_path: str,
                 raw_device_path: str, size_bytes: int = 0):
        self.device_identifier = device_identifier
        self.device_path = device_path
        self.raw_device_path = raw_device_path
        self.size_bytes = size_bytes

    def full_check(self, progress_callback=None) -> HealthReport:
        """Run all health checks and return a combined report."""
        report = HealthReport(device_identifier=self.device_identifier)

        # Step 1: diskutil verifyVolume
        report.details.append("── diskutil verifyVolume ──")
        verify_ok = self._run_verify_volume(report)

        # Step 2: Probe sectors
        report.details.append("")
        report.details.append("── Sector probe ──")
        probe_ok = self._probe_sectors(report, progress_callback)

        # Determine overall status
        if verify_ok and probe_ok:
            report.status = HealthStatus.HEALTHY
            report.summary = "Filesystem appears healthy. No issues detected."
        elif not verify_ok and probe_ok:
            report.status = HealthStatus.WARNING
            report.summary = ("Filesystem verification reported issues, "
                              "but sectors are readable. Possible minor corruption.")
        elif verify_ok and not probe_ok:
            report.status = HealthStatus.WARNING
            report.summary = ("Filesystem verifies OK, but some sectors "
                              "are unreadable. Possible hardware damage.")
        else:
            report.status = HealthStatus.CORRUPTED
            report.summary = ("Filesystem corruption detected AND sectors "
                              "are unreadable. Drive is likely corrupted.")

        return report

    def _run_verify_volume(self, report: HealthReport) -> bool:
        """Run diskutil verifyVolume and parse the result."""
        try:
            result = subprocess.run(
                ["diskutil", "verifyVolume", self.device_identifier],
                capture_output=True, text=True, timeout=120
            )
            output = result.stdout + result.stderr
            report.raw_output = output

            if result.returncode == 0:
                report.details.append("✅ Volume verification passed.")
                return True
            else:
                report.details.append("❌ Volume verification FAILED.")
                # Extract key error lines
                for line in output.splitlines():
                    line = line.strip()
                    if any(kw in line.lower() for kw in [
                        "invalid", "error", "corrupt", "damaged",
                        "repair", "fail", "problem", "incorrect"
                    ]):
                        report.details.append(f"   → {line}")
                return False

        except subprocess.TimeoutExpired:
            report.details.append("⚠️  Verification timed out (120s).")
            return False
        except FileNotFoundError:
            report.details.append("⚠️  diskutil not available.")
            return False
        except Exception as e:
            report.details.append(f"⚠️  Verification error: {e}")
            return False

    def _probe_sectors(self, report: HealthReport, progress_callback=None) -> bool:
        """Try to read key sectors from the raw device."""
        if self.size_bytes <= 0:
            report.details.append("⚠️  Unknown device size — skipping probe.")
            return True

        # We probe: first 1 MB, last 1 MB, and ~8 evenly spaced spots
        chunk = 1024 * 1024  # 1 MB
        offsets = [0]  # first

        if self.size_bytes > chunk:
            offsets.append(self.size_bytes - chunk)  # last

        # 8 evenly spaced interior samples
        if self.size_bytes > chunk * 10:
            step = self.size_bytes // 10
            for i in range(1, 9):
                offsets.append(step * i)

        offsets = sorted(set(offsets))
        report.total_probed = len(offsets)
        readable = 0
        failed = 0

        try:
            fd = os.open(self.raw_device_path, os.O_RDONLY)
        except PermissionError:
            # Try the non-raw path
            try:
                fd = os.open(self.device_path, os.O_RDONLY)
            except PermissionError:
                report.details.append(
                    "⚠️  Permission denied — run with sudo for full probe.")
                return True  # Can't tell, assume OK
            except Exception as e:
                report.details.append(f"⚠️  Cannot open device: {e}")
                return True
        except Exception as e:
            report.details.append(f"⚠️  Cannot open device: {e}")
            return True

        try:
            for idx, offset in enumerate(offsets):
                try:
                    os.lseek(fd, offset, os.SEEK_SET)
                    data = os.read(fd, min(chunk, self.size_bytes - offset))
                    if len(data) > 0:
                        readable += 1
                    else:
                        failed += 1
                        report.details.append(
                            f"   ❌ Empty read at offset {offset:,}")
                except OSError as e:
                    failed += 1
                    report.details.append(
                        f"   ❌ Read error at offset {offset:,}: {e}")

                if progress_callback:
                    progress_callback(idx + 1, len(offsets))
        finally:
            os.close(fd)

        report.readable_sectors = readable
        report.failed_sectors = failed

        if failed == 0:
            report.details.append(
                f"✅ All {readable} probed regions readable.")
            return True
        else:
            report.details.append(
                f"❌ {failed}/{report.total_probed} probed regions failed.")
            return False
