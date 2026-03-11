"""
File Signatures Database
Defines magic bytes (headers/footers) for ~40+ file types used during file carving.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FileSignature:
    """Represents a known file type signature."""
    name: str
    extension: str
    category: str  # Image, Document, Audio, Video, Archive, Database, Executable, Other
    header: bytes
    footer: Optional[bytes] = None
    max_size: int = 50 * 1024 * 1024  # Default 50 MB max
    description: str = ""
    header_offset: int = 0  # Some signatures don't start at byte 0


# ──────────────────────────────────────────────
# MASTER SIGNATURE DATABASE
# ──────────────────────────────────────────────

SIGNATURES: list[FileSignature] = [
    # ═══════════════ IMAGES ═══════════════
    FileSignature(
        name="JPEG", extension=".jpg", category="Image",
        header=b"\xFF\xD8\xFF",
        footer=b"\xFF\xD9",
        max_size=30 * 1024 * 1024,
        description="JPEG image",
    ),
    FileSignature(
        name="PNG", extension=".png", category="Image",
        header=b"\x89PNG\r\n\x1a\n",
        footer=b"IEND\xAE\x42\x60\x82",
        max_size=30 * 1024 * 1024,
        description="PNG image",
    ),
    FileSignature(
        name="GIF87a", extension=".gif", category="Image",
        header=b"GIF87a",
        footer=b"\x00\x3B",
        max_size=20 * 1024 * 1024,
        description="GIF image (87a)",
    ),
    FileSignature(
        name="GIF89a", extension=".gif", category="Image",
        header=b"GIF89a",
        footer=b"\x00\x3B",
        max_size=20 * 1024 * 1024,
        description="GIF image (89a)",
    ),
    FileSignature(
        name="BMP", extension=".bmp", category="Image",
        header=b"BM",
        max_size=50 * 1024 * 1024,
        description="Bitmap image",
    ),
    FileSignature(
        name="TIFF (LE)", extension=".tiff", category="Image",
        header=b"\x49\x49\x2A\x00",
        max_size=100 * 1024 * 1024,
        description="TIFF image (little-endian)",
    ),
    FileSignature(
        name="TIFF (BE)", extension=".tiff", category="Image",
        header=b"\x4D\x4D\x00\x2A",
        max_size=100 * 1024 * 1024,
        description="TIFF image (big-endian)",
    ),
    FileSignature(
        name="WEBP", extension=".webp", category="Image",
        header=b"RIFF",  # Followed by size + "WEBP" — validated in carver
        max_size=30 * 1024 * 1024,
        description="WebP image",
    ),
    FileSignature(
        name="ICO", extension=".ico", category="Image",
        header=b"\x00\x00\x01\x00",
        max_size=1 * 1024 * 1024,
        description="Windows icon",
    ),
    FileSignature(
        name="SVG", extension=".svg", category="Image",
        header=b"<svg",
        max_size=5 * 1024 * 1024,
        description="SVG vector image",
    ),

    # ═══════════════ DOCUMENTS ═══════════════
    FileSignature(
        name="PDF", extension=".pdf", category="Document",
        header=b"%PDF",
        footer=b"%%EOF",
        max_size=200 * 1024 * 1024,
        description="PDF document",
    ),
    FileSignature(
        name="DOCX/XLSX/PPTX/ZIP", extension=".zip", category="Archive",
        header=b"PK\x03\x04",
        footer=b"PK\x05\x06",
        max_size=200 * 1024 * 1024,
        description="ZIP archive (or Office document)",
    ),
    FileSignature(
        name="RTF", extension=".rtf", category="Document",
        header=b"{\\rtf",
        footer=b"}",
        max_size=50 * 1024 * 1024,
        description="Rich Text Format",
    ),
    FileSignature(
        name="OLE2 (DOC/XLS/PPT)", extension=".doc", category="Document",
        header=b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1",
        max_size=100 * 1024 * 1024,
        description="Microsoft OLE2 compound document",
    ),

    # ═══════════════ AUDIO ═══════════════
    FileSignature(
        name="MP3 (ID3)", extension=".mp3", category="Audio",
        header=b"ID3",
        max_size=50 * 1024 * 1024,
        description="MP3 audio with ID3 tag",
    ),
    FileSignature(
        name="MP3 (sync)", extension=".mp3", category="Audio",
        header=b"\xFF\xFB",
        max_size=50 * 1024 * 1024,
        description="MP3 audio (sync frame)",
    ),
    FileSignature(
        name="WAV", extension=".wav", category="Audio",
        header=b"RIFF",  # Followed by size + "WAVE"
        max_size=500 * 1024 * 1024,
        description="WAV audio",
    ),
    FileSignature(
        name="FLAC", extension=".flac", category="Audio",
        header=b"fLaC",
        max_size=200 * 1024 * 1024,
        description="FLAC lossless audio",
    ),
    FileSignature(
        name="OGG", extension=".ogg", category="Audio",
        header=b"OggS",
        max_size=100 * 1024 * 1024,
        description="OGG Vorbis audio",
    ),
    FileSignature(
        name="MIDI", extension=".mid", category="Audio",
        header=b"MThd",
        max_size=5 * 1024 * 1024,
        description="MIDI music file",
    ),
    FileSignature(
        name="AAC (ADTS)", extension=".aac", category="Audio",
        header=b"\xFF\xF1",
        max_size=50 * 1024 * 1024,
        description="AAC audio",
    ),

    # ═══════════════ VIDEO ═══════════════
    FileSignature(
        name="MP4/MOV", extension=".mp4", category="Video",
        header=b"\x00\x00\x00",  # ftyp box — refined in carver
        max_size=2 * 1024 * 1024 * 1024,  # 2 GB
        description="MP4/MOV video container",
    ),
    FileSignature(
        name="AVI", extension=".avi", category="Video",
        header=b"RIFF",  # Followed by size + "AVI "
        max_size=2 * 1024 * 1024 * 1024,
        description="AVI video",
    ),
    FileSignature(
        name="MKV", extension=".mkv", category="Video",
        header=b"\x1A\x45\xDF\xA3",
        max_size=2 * 1024 * 1024 * 1024,
        description="Matroska video container",
    ),
    FileSignature(
        name="FLV", extension=".flv", category="Video",
        header=b"FLV\x01",
        max_size=500 * 1024 * 1024,
        description="Flash video",
    ),
    FileSignature(
        name="WMV/ASF", extension=".wmv", category="Video",
        header=b"\x30\x26\xB2\x75\x8E\x66\xCF\x11",
        max_size=1 * 1024 * 1024 * 1024,
        description="Windows Media Video",
    ),

    # ═══════════════ ARCHIVES ═══════════════
    FileSignature(
        name="RAR5", extension=".rar", category="Archive",
        header=b"Rar!\x1A\x07\x01\x00",
        max_size=500 * 1024 * 1024,
        description="RAR archive v5",
    ),
    FileSignature(
        name="RAR4", extension=".rar", category="Archive",
        header=b"Rar!\x1A\x07\x00",
        max_size=500 * 1024 * 1024,
        description="RAR archive v4",
    ),
    FileSignature(
        name="7Z", extension=".7z", category="Archive",
        header=b"7z\xBC\xAF\x27\x1C",
        max_size=500 * 1024 * 1024,
        description="7-Zip archive",
    ),
    FileSignature(
        name="GZIP", extension=".gz", category="Archive",
        header=b"\x1F\x8B",
        max_size=500 * 1024 * 1024,
        description="GZIP compressed file",
    ),
    FileSignature(
        name="BZIP2", extension=".bz2", category="Archive",
        header=b"BZh",
        max_size=500 * 1024 * 1024,
        description="BZIP2 compressed file",
    ),
    FileSignature(
        name="XZ", extension=".xz", category="Archive",
        header=b"\xFD7zXZ\x00",
        max_size=500 * 1024 * 1024,
        description="XZ compressed file",
    ),
    FileSignature(
        name="TAR", extension=".tar", category="Archive",
        header=b"ustar",
        header_offset=257,
        max_size=1 * 1024 * 1024 * 1024,
        description="TAR archive",
    ),

    # ═══════════════ DATABASE ═══════════════
    FileSignature(
        name="SQLite", extension=".sqlite", category="Database",
        header=b"SQLite format 3\x00",
        max_size=500 * 1024 * 1024,
        description="SQLite database",
    ),

    # ═══════════════ EXECUTABLES ═══════════════
    FileSignature(
        name="EXE/DLL (PE)", extension=".exe", category="Executable",
        header=b"MZ",
        max_size=200 * 1024 * 1024,
        description="Windows executable",
    ),
    FileSignature(
        name="ELF", extension=".elf", category="Executable",
        header=b"\x7FELF",
        max_size=200 * 1024 * 1024,
        description="Linux ELF executable",
    ),
    FileSignature(
        name="Mach-O (64-bit)", extension=".macho", category="Executable",
        header=b"\xCF\xFA\xED\xFE",
        max_size=200 * 1024 * 1024,
        description="macOS Mach-O binary",
    ),

    # ═══════════════ OTHER ═══════════════
    FileSignature(
        name="XML", extension=".xml", category="Other",
        header=b"<?xml",
        max_size=50 * 1024 * 1024,
        description="XML document",
    ),
    FileSignature(
        name="HTML", extension=".html", category="Other",
        header=b"<!DOCTYPE html",
        max_size=10 * 1024 * 1024,
        description="HTML document",
    ),
    FileSignature(
        name="PSD", extension=".psd", category="Image",
        header=b"8BPS",
        max_size=500 * 1024 * 1024,
        description="Adobe Photoshop document",
    ),
    FileSignature(
        name="DMG", extension=".dmg", category="Archive",
        header=b"koly",
        max_size=2 * 1024 * 1024 * 1024,
        description="macOS disk image (trailer)",
    ),
]


def get_signatures_by_category(category: str) -> list[FileSignature]:
    """Return all signatures matching a given category."""
    return [s for s in SIGNATURES if s.category.lower() == category.lower()]


def get_all_categories() -> list[str]:
    """Return sorted unique list of categories."""
    return sorted(set(s.category for s in SIGNATURES))


def get_max_header_length() -> int:
    """Return the length of the longest header for overlap calculation."""
    return max(len(s.header) + s.header_offset for s in SIGNATURES)
