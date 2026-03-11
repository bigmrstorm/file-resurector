"""
File Carver
Scans raw device bytes to find files by their magic byte signatures.
"""

import os
import time
import threading
from dataclasses import dataclass, field
from typing import Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.file_signatures import SIGNATURES, FileSignature, get_max_header_length


@dataclass
class CarvedFile:
    """Represents a file found during carving."""
    offset: int
    size: int
    file_type: str
    extension: str
    category: str
    confidence: float  # 0.0 – 1.0
    signature_name: str
    description: str = ""

    @property
    def size_human(self) -> str:
        size = self.size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    @property
    def confidence_pct(self) -> str:
        return f"{self.confidence * 100:.0f}%"


class ScanConfig:
    """Configuration for a carving scan."""
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"

    def __init__(self, depth: str = "standard",
                 categories: Optional[list[str]] = None,
                 chunk_size: int = 4 * 1024 * 1024,  # 4 MB — big reads = fast
                 max_workers: int = 2):
        self.depth = depth
        self.categories = categories  # None = all
        self.chunk_size = chunk_size
        self.max_workers = max_workers

        # Depth controls how much of the disk we scan
        if depth == self.QUICK:
            self.scan_fraction = 0.1   # First/last 5% each
        elif depth == self.DEEP:
            self.scan_fraction = 1.0   # Full scan
        else:
            self.scan_fraction = 0.5   # First/last 25% each


@dataclass
class ScanProgress:
    """Real-time progress information for the UI."""
    bytes_scanned: int = 0
    total_bytes: int = 0
    files_found: int = 0
    current_offset: int = 0
    speed_bps: float = 0.0
    elapsed_seconds: float = 0.0
    is_complete: bool = False
    error: Optional[str] = None

    @property
    def progress_fraction(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return min(self.bytes_scanned / self.total_bytes, 1.0)

    @property
    def progress_pct(self) -> str:
        return f"{self.progress_fraction * 100:.1f}%"

    @property
    def eta_seconds(self) -> float:
        if self.speed_bps <= 0:
            return 0
        remaining = self.total_bytes - self.bytes_scanned
        return remaining / self.speed_bps

    @property
    def speed_human(self) -> str:
        speed = self.speed_bps
        for unit in ["B/s", "KB/s", "MB/s", "GB/s"]:
            if speed < 1024:
                return f"{speed:.1f} {unit}"
            speed /= 1024
        return f"{speed:.1f} TB/s"

    @property
    def eta_human(self) -> str:
        eta = self.eta_seconds
        if eta <= 0:
            return "—"
        if eta < 60:
            return f"{eta:.0f}s"
        elif eta < 3600:
            return f"{eta / 60:.0f}m {eta % 60:.0f}s"
        else:
            return f"{eta / 3600:.0f}h {(eta % 3600) / 60:.0f}m"


class FileCarver:
    """Carves files from raw device bytes using signature matching."""

    def __init__(self, device_path: str, size_bytes: int, config: ScanConfig = None):
        self.device_path = device_path
        self.size_bytes = size_bytes
        self.config = config or ScanConfig()
        self._stop_event = threading.Event()
        self._results: list[CarvedFile] = []
        self._results_lock = threading.Lock()
        self._progress = ScanProgress(total_bytes=size_bytes)
        self._last_progress_time = 0.0  # Throttle progress callbacks

        # Filter signatures by selected categories
        if self.config.categories:
            cats = [c.lower() for c in self.config.categories]
            self._signatures = [s for s in SIGNATURES
                                if s.category.lower() in cats]
        else:
            self._signatures = list(SIGNATURES)

        self._overlap = get_max_header_length() + 16

        # Pre-build a set of all first-byte values for fast rejection
        self._header_first_bytes = set()
        self._min_header_len = 999
        for sig in self._signatures:
            self._header_first_bytes.add(sig.header[0])
            self._min_header_len = min(self._min_header_len, len(sig.header))

    def scan(self, progress_callback: Optional[Callable[[ScanProgress], None]] = None
             ) -> list[CarvedFile]:
        """
        Run the scan synchronously.
        Returns list of CarvedFile when complete.
        """
        self._stop_event.clear()
        self._results.clear()
        self._progress = ScanProgress(total_bytes=self._get_scan_bytes())

        start_time = time.time()

        # Try multiple device path variants for robustness
        # macOS raw character devices (/dev/rdisk4) are faster for raw I/O,
        # but sometimes only the block device (/dev/disk4) works.
        paths_to_try = [self.device_path]

        # If the path is a raw device, also try the block device and vice versa
        if "/dev/r" in self.device_path:
            block_path = self.device_path.replace("/dev/r", "/dev/")
            if block_path not in paths_to_try:
                paths_to_try.append(block_path)
        elif "/dev/" in self.device_path:
            raw_path = self.device_path.replace("/dev/", "/dev/r")
            if raw_path not in paths_to_try:
                paths_to_try.insert(0, raw_path)

        fd = None
        opened_path = None
        for path in paths_to_try:
            try:
                print(f"[FileCarver] Trying to open: {path}")
                fd = os.open(path, os.O_RDONLY)
                opened_path = path
                # Bypass macOS disk cache for faster sequential raw I/O
                try:
                    import fcntl
                    fcntl.fcntl(fd, fcntl.F_NOCACHE, 1)
                except Exception:
                    pass
                print(f"[FileCarver] Successfully opened: {path}")
                break
            except PermissionError:
                print(f"[FileCarver] Permission denied: {path}")
                continue
            except Exception as e:
                print(f"[FileCarver] Cannot open {path}: {e}")
                continue

        if fd is None:
            self._progress.error = (
                "Permission denied. Run with: sudo ./venv/bin/python3 main.py"
            )
            self._progress.is_complete = True
            if progress_callback:
                progress_callback(self._progress)
            return []

        try:
            # Verify we can actually read from the device
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                test_read = os.read(fd, 512)
                if not test_read:
                    self._progress.error = f"Device {opened_path} returned empty data"
                    self._progress.is_complete = True
                    if progress_callback:
                        progress_callback(self._progress)
                    return []
                print(f"[FileCarver] Test read OK: {len(test_read)} bytes from {opened_path}")
            except Exception as e:
                self._progress.error = f"Cannot read from device: {e}"
                self._progress.is_complete = True
                if progress_callback:
                    progress_callback(self._progress)
                return []

            regions = self._get_scan_regions()
            print(f"[FileCarver] Scanning {len(regions)} region(s), "
                  f"total {self._get_scan_bytes()} bytes, "
                  f"{len(self._signatures)} signatures")
            for region_start, region_end in regions:
                if self._stop_event.is_set():
                    break
                self._scan_region(fd, region_start, region_end,
                                  start_time, progress_callback)
        finally:
            os.close(fd)

        self._progress.is_complete = True
        self._progress.elapsed_seconds = time.time() - start_time
        print(f"[FileCarver] Scan complete: {len(self._results)} files found "
              f"in {self._progress.elapsed_seconds:.1f}s")
        if progress_callback:
            progress_callback(self._progress)

        return sorted(self._results, key=lambda f: f.offset)

    def scan_async(self, progress_callback: Optional[Callable[[ScanProgress], None]] = None,
                   done_callback: Optional[Callable[[list[CarvedFile]], None]] = None):
        """Start scan in a background thread."""
        def _worker():
            results = self.scan(progress_callback)
            if done_callback:
                done_callback(results)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return t

    def stop(self):
        """Signal the scan to stop."""
        self._stop_event.set()

    @property
    def results(self) -> list[CarvedFile]:
        with self._results_lock:
            return list(self._results)

    @property
    def progress(self) -> ScanProgress:
        return self._progress

    # ─── Internal ───────────────────────────────────

    def _get_scan_bytes(self) -> int:
        """Calculate how many bytes we'll actually scan based on depth."""
        if self.config.depth == ScanConfig.DEEP:
            return self.size_bytes
        return int(self.size_bytes * self.config.scan_fraction)

    def _get_scan_regions(self) -> list[tuple[int, int]]:
        """Return (start, end) byte ranges to scan."""
        if self.config.depth == ScanConfig.DEEP:
            return [(0, self.size_bytes)]

        fraction = self.config.scan_fraction / 2
        front_end = int(self.size_bytes * fraction)
        back_start = self.size_bytes - int(self.size_bytes * fraction)

        regions = [(0, min(front_end, self.size_bytes))]
        if back_start > front_end:
            regions.append((back_start, self.size_bytes))
        return regions

    def _scan_region(self, fd: int, start: int, end: int,
                     start_time: float,
                      progress_callback: Optional[Callable] = None):
        """Scan a byte region for file signatures."""
        chunk_size = self.config.chunk_size
        offset = start
        prev_tail = b""

        while offset < end and not self._stop_event.is_set():
            read_size = min(chunk_size, end - offset)
            try:
                os.lseek(fd, offset, os.SEEK_SET)
                data = os.read(fd, read_size)
            except OSError:
                offset += read_size
                continue

            if not data:
                break

            # Combine with tail of previous chunk to catch split headers
            search_data = prev_tail + data
            search_base = offset - len(prev_tail)

            # Search for every signature in this chunk
            for sig in self._signatures:
                self._find_signature_in_chunk(
                    fd, search_data, search_base, sig, end
                )

            # Keep tail for overlap
            prev_tail = data[-self._overlap:] if len(data) >= self._overlap else data

            offset += len(data)

            # Update progress
            now = time.time()
            elapsed = now - start_time
            self._progress.bytes_scanned += len(data)
            self._progress.current_offset = offset
            self._progress.elapsed_seconds = elapsed
            if elapsed > 0:
                self._progress.speed_bps = self._progress.bytes_scanned / elapsed
            self._progress.files_found = len(self._results)

            # Throttle progress callbacks to max 4/sec to reduce UI overhead
            if progress_callback and (now - self._last_progress_time) >= 0.25:
                self._last_progress_time = now
                progress_callback(self._progress)

    def _find_signature_in_chunk(self, fd: int, data: bytes,
                                 base_offset: int, sig: FileSignature,
                                 region_end: int):
        """Find all occurrences of a signature header in a data chunk."""
        header = sig.header
        search_start = 0

        while True:
            pos = data.find(header, search_start)
            if pos == -1:
                break

            absolute_offset = base_offset + pos

            # Skip if this offset has a header_offset requirement
            if sig.header_offset > 0:
                actual_start = absolute_offset - sig.header_offset
                if actual_start < 0:
                    search_start = pos + 1
                    continue
                absolute_offset = actual_start

            # Structural validation — reject false positives early
            if not self._validate_signature(data, pos, sig):
                search_start = pos + 1
                continue

            # Determine file size
            file_size = self._determine_file_size(fd, absolute_offset, sig, region_end)
            if file_size <= 0 or file_size < 64:
                search_start = pos + 1
                continue

            # Calculate confidence
            confidence = self._calculate_confidence(fd, absolute_offset, file_size, sig)

            # ── MINIMUM CONFIDENCE FILTER ──
            # Skip anything below 40% — it's almost certainly a false positive
            if confidence < 0.40:
                search_start = pos + 1
                continue

            carved = CarvedFile(
                offset=absolute_offset,
                size=file_size,
                file_type=sig.name,
                extension=sig.extension,
                category=sig.category,
                confidence=confidence,
                signature_name=sig.name,
                description=sig.description,
            )

            with self._results_lock:
                # Avoid duplicates (same offset ± 512 bytes)
                if not any(abs(r.offset - carved.offset) < 512 for r in self._results):
                    self._results.append(carved)

            search_start = pos + 1

    def _validate_signature(self, data: bytes, pos: int, sig: FileSignature) -> bool:
        """Structural validation for each file format to reject false positives."""

        # ── RIFF family (WEBP, WAV, AVI) ──
        if sig.header == b"RIFF" and pos + 12 <= len(data):
            sub_type = data[pos + 8:pos + 12]
            if sig.name == "WEBP" and sub_type != b"WEBP":
                return False
            if sig.name == "WAV" and sub_type != b"WAVE":
                return False
            if sig.name == "AVI" and sub_type != b"AVI ":
                return False
            # Also validate that the RIFF size field is sane
            if pos + 8 <= len(data):
                riff_size = int.from_bytes(data[pos + 4:pos + 8], "little")
                if riff_size < 12 or riff_size > 2 * 1024 * 1024 * 1024:
                    return False

        # ── BMP: validate header structure ──
        if sig.name == "BMP" and pos + 26 <= len(data):
            # Bytes 2-5: file size (LE uint32) — must be reasonable
            bmp_size = int.from_bytes(data[pos + 2:pos + 6], "little")
            if bmp_size < 54 or bmp_size > 200 * 1024 * 1024:
                return False
            # Bytes 6-9: reserved, must be 0
            reserved = int.from_bytes(data[pos + 6:pos + 10], "little")
            if reserved != 0:
                return False
            # Bytes 10-13: data offset — typically 54 or larger
            data_offset = int.from_bytes(data[pos + 10:pos + 14], "little")
            if data_offset < 26 or data_offset > bmp_size:
                return False
            # Bytes 14-17: DIB header size — must be a known value
            dib_size = int.from_bytes(data[pos + 14:pos + 18], "little")
            if dib_size not in (12, 40, 52, 56, 108, 124):
                return False
            # Bytes 18-21: width, 22-25: height — must be reasonable
            width = int.from_bytes(data[pos + 18:pos + 22], "little", signed=True)
            height = int.from_bytes(data[pos + 22:pos + 26], "little", signed=True)
            if abs(width) > 32768 or abs(height) > 32768 or width == 0 or height == 0:
                return False

        # ── MP4/MOV: check for 'ftyp' at offset +4 and valid brand ──
        if sig.name == "MP4/MOV" and pos + 16 <= len(data):
            if data[pos + 4:pos + 8] != b"ftyp":
                return False
            # Check the brand is a known ftyp brand
            brand = data[pos + 8:pos + 12]
            known_brands = {
                b"isom", b"iso2", b"iso3", b"iso4", b"iso5", b"iso6",
                b"mp41", b"mp42", b"mp71",
                b"M4A ", b"M4B ", b"M4P ", b"M4V ", b"M4VH", b"M4VP",
                b"mmp4", b"avc1", b"3gp4", b"3gp5", b"3gp6", b"3gp7",
                b"3gs7", b"3ge6", b"3ge7", b"3gg6",
                b"qt  ", b"MSNV", b"dash", b"dby1",
                b"f4v ", b"f4p ", b"NDSC", b"NDSH", b"NDSM", b"NDSP",
                b"NDSS", b"NDXS", b"NDXH", b"NDXM", b"NDXP",
                b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis",
                b"avif", b"mif1", b"msf1",
                b"crx ", b"craw",  # Canon RAW
            }
            if brand not in known_brands:
                # Fallback: check if brand is printable ASCII
                if not all(32 <= b < 127 for b in brand):
                    return False
            # Also validate the box size at bytes 0-3
            box_size = int.from_bytes(data[pos:pos + 4], "big")
            if box_size < 8 or box_size > 100 * 1024 * 1024:
                return False

        # ── MP3 sync frame: validate frame header bits ──
        if sig.name == "MP3 (sync)" and pos + 4 <= len(data):
            b1 = data[pos + 1]
            b2 = data[pos + 2]
            # Bits 3-4 of byte 1: MPEG version, must not be 01 (reserved)
            version = (b1 >> 3) & 0x03
            if version == 1:
                return False
            # Bits 1-2 of byte 1: layer, must not be 00 (reserved)
            layer = (b1 >> 1) & 0x03
            if layer == 0:
                return False
            # Bits 4-7 of byte 2: bitrate index, must not be 0xF (bad)
            bitrate_idx = (b2 >> 4) & 0x0F
            if bitrate_idx == 0x0F or bitrate_idx == 0:
                return False
            # Bits 2-3 of byte 2: sample rate index, must not be 0x3 (reserved)
            sample_idx = (b2 >> 2) & 0x03
            if sample_idx == 3:
                return False

        # ── AAC ADTS: validate frame header ──
        if sig.name == "AAC (ADTS)" and pos + 4 <= len(data):
            b1 = data[pos + 1]
            # Bits 1-2: layer, must be 0
            if (b1 >> 1) & 0x03 != 0:
                return False

        # ── GZIP: validate compression method and flags ──
        if sig.name == "GZIP" and pos + 10 <= len(data):
            method = data[pos + 2]
            flags = data[pos + 3]
            if method != 8:  # Only deflate is valid
                return False
            if flags & 0xE0:  # Reserved bits must be 0
                return False

        # ── ICO: validate image entries structure ──
        if sig.name == "ICO" and pos + 22 <= len(data):
            img_count = int.from_bytes(data[pos + 4:pos + 6], "little")
            if img_count == 0 or img_count > 50:  # Tighter limit
                return False
            # Validate first image directory entry (starts at offset 6)
            # Each entry: 1B width, 1B height, 1B color_count, 1B reserved(0),
            #             2B color_planes, 2B bits_per_pixel, 4B size, 4B offset
            entry_start = pos + 6
            if entry_start + 16 <= len(data):
                reserved = data[entry_start + 3]
                if reserved != 0:
                    return False
                ico_data_size = int.from_bytes(data[entry_start + 8:entry_start + 12], "little")
                ico_data_offset = int.from_bytes(data[entry_start + 12:entry_start + 16], "little")
                # Data size and offset must be reasonable
                if ico_data_size == 0 or ico_data_size > 10 * 1024 * 1024:
                    return False
                if ico_data_offset < 6 + (img_count * 16):
                    return False

        # ── PSD: validate version and channels ──
        if sig.name == "PSD" and pos + 26 <= len(data):
            # Bytes 4-5: version (must be 1 for PSD or 2 for PSB)
            version = int.from_bytes(data[pos + 4:pos + 6], "big")
            if version not in (1, 2):
                return False
            # Bytes 6-11: reserved, must be zero
            reserved = data[pos + 6:pos + 12]
            if reserved != b"\x00" * 6:
                return False
            # Bytes 12-13: channels (1-56)
            channels = int.from_bytes(data[pos + 12:pos + 14], "big")
            if channels == 0 or channels > 56:
                return False
            # Bytes 14-17: height, 18-21: width (1 to 300000)
            height = int.from_bytes(data[pos + 14:pos + 18], "big")
            width = int.from_bytes(data[pos + 18:pos + 22], "big")
            if height == 0 or height > 300000 or width == 0 or width > 300000:
                return False

        # ── EXE/DLL (PE): check PE signature offset ──
        if sig.name == "EXE/DLL (PE)" and pos + 64 <= len(data):
            pe_offset = int.from_bytes(data[pos + 60:pos + 64], "little")
            if pe_offset < 64 or pe_offset > 1024:
                return False

        return True

    def _determine_file_size(self, fd: int, offset: int,
                             sig: FileSignature, region_end: int) -> int:
        """Determine file size using footer search, header metadata, or capped default."""
        max_search = min(sig.max_size, region_end - offset)

        # 1. Try to read size from header metadata first (BMP, RIFF)
        size = self._try_read_size_from_header(fd, offset, sig)
        if size and 64 <= size <= max_search:
            return size

        # 2. Search for footer if the format has one
        if sig.footer:
            search_chunk = 512 * 1024  # 512 KB at a time
            searched = len(sig.header)

            while searched < max_search:
                read_size = min(search_chunk, max_search - searched)
                try:
                    os.lseek(fd, offset + searched, os.SEEK_SET)
                    chunk = os.read(fd, read_size)
                except OSError:
                    break

                if not chunk:
                    break

                footer_pos = chunk.find(sig.footer)
                if footer_pos != -1:
                    return searched + footer_pos + len(sig.footer)

                # Overlap to catch split footers
                searched += len(chunk) - len(sig.footer)

            # Footer format but no footer found — this is suspicious
            # Don't return max_size, return 0 to skip it
            return 0

        # 3. No footer and no header size: use a conservative cap
        # For formats without footers, we cap reasonably rather than using max_size
        # which would produce tons of huge false positives
        conservative_caps = {
            "BMP": 10 * 1024 * 1024,
            "TIFF (LE)": 20 * 1024 * 1024,
            "TIFF (BE)": 20 * 1024 * 1024,
            "MP3 (ID3)": 15 * 1024 * 1024,
            "MP3 (sync)": 10 * 1024 * 1024,
            "FLAC": 50 * 1024 * 1024,
            "MIDI": 2 * 1024 * 1024,
            "AAC (ADTS)": 15 * 1024 * 1024,
            "MKV": 500 * 1024 * 1024,
            "ICO": 512 * 1024,
        }
        cap = conservative_caps.get(sig.name, min(sig.max_size, 10 * 1024 * 1024))
        return min(cap, max_search)

    def _try_read_size_from_header(self, fd: int, offset: int,
                                   sig: FileSignature) -> Optional[int]:
        """Try to extract file size from the file's own header metadata."""
        try:
            os.lseek(fd, offset, os.SEEK_SET)
            header_data = os.read(fd, 64)  # Read first 64 bytes
        except OSError:
            return None

        # BMP: size at bytes 2-5 (little-endian uint32)
        if sig.name == "BMP" and len(header_data) >= 6:
            size = int.from_bytes(header_data[2:6], "little")
            # Sanity: BMP size must be at least 54 bytes (minimum header)
            if 54 <= size <= 200 * 1024 * 1024:
                return size
            return None

        # RIFF (WAV, AVI, WEBP): size at bytes 4-7 (little-endian uint32) + 8
        if sig.header == b"RIFF" and len(header_data) >= 8:
            size = int.from_bytes(header_data[4:8], "little") + 8
            if 12 <= size <= 2 * 1024 * 1024 * 1024:
                return size
            return None

        # MP4/MOV: first box size at bytes 0-3 (big-endian uint32)
        if sig.name == "MP4/MOV" and len(header_data) >= 8:
            box_size = int.from_bytes(header_data[0:4], "big")
            if 8 <= box_size <= 100 * 1024 * 1024:
                # This is just the ftyp box, actual file is much larger
                # Can't reliably determine full size from just ftyp
                return None

        return None

    def _calculate_confidence(self, fd: int, offset: int,
                              size: int, sig: FileSignature) -> float:
        """Calculate a confidence score for a recovered file."""
        confidence = 0.3  # Lower base

        # Longer headers = more reliable match
        header_len = len(sig.header)
        if header_len >= 8:
            confidence += 0.25
        elif header_len >= 4:
            confidence += 0.15
        elif header_len >= 3:
            confidence += 0.05
        # 2-byte headers get no bonus (BM, \xFF\xFB, etc.)

        # Has footer and we found it? Major confidence boost
        if sig.footer:
            confidence += 0.15

        # Reasonable size (not exactly at the cap)?
        if 100 < size < sig.max_size * 0.8:
            confidence += 0.1

        # Size was read from header metadata? Very confident
        header_size = self._try_read_size_from_header(fd, offset, sig)
        if header_size and abs(header_size - size) < 100:
            confidence += 0.15

        # Can we read the data, and is it not garbage?
        try:
            os.lseek(fd, offset, os.SEEK_SET)
            sample = os.read(fd, min(4096, size))
            if len(sample) > 0:
                confidence += 0.05
                # Check it's not all zeros or all 0xFF
                if sample != b"\x00" * len(sample) and sample != b"\xFF" * len(sample):
                    confidence += 0.05
                # Check entropy — real files have varied byte values
                unique_bytes = len(set(sample[:512]))
                if unique_bytes > 10:
                    confidence += 0.05
        except OSError:
            confidence -= 0.2

        return min(confidence, 1.0)
