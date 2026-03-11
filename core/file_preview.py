"""
File Preview
Generates previews for recovered/carved files — image thumbnails, text excerpts, hex fallback.
"""

import os
import io
from typing import Optional

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class FilePreview:
    """Generate preview data for a file based on its type."""

    # Max preview sizes
    THUMB_SIZE = (200, 200)
    TEXT_PREVIEW_BYTES = 2048
    HEX_PREVIEW_BYTES = 256

    # Text-like extensions
    TEXT_EXTENSIONS = {
        ".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm",
        ".py", ".js", ".css", ".log", ".rtf", ".yaml", ".yml",
        ".ini", ".cfg", ".conf", ".sh", ".bat", ".sql",
    }

    # Image extensions PIL can handle
    IMAGE_EXTENSIONS = {
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif",
        ".webp", ".ico", ".psd",
    }

    @staticmethod
    def can_preview(extension: str) -> bool:
        """Check if we can generate a preview for this file type."""
        ext = extension.lower()
        if ext in FilePreview.IMAGE_EXTENSIONS and HAS_PIL:
            return True
        if ext in FilePreview.TEXT_EXTENSIONS:
            return True
        return True  # Hex fallback always works

    @staticmethod
    def get_preview_type(extension: str) -> str:
        """Return the type of preview available: 'image', 'text', or 'hex'."""
        ext = extension.lower()
        if ext in FilePreview.IMAGE_EXTENSIONS and HAS_PIL:
            return "image"
        if ext in FilePreview.TEXT_EXTENSIONS:
            return "text"
        return "hex"

    @staticmethod
    def generate_image_thumbnail(file_path: str = None, raw_data: bytes = None,
                                  size: tuple = None) -> Optional[object]:
        """
        Generate a PIL Image thumbnail.
        Accepts either a file path or raw bytes.
        Returns a PIL Image or None.
        """
        if not HAS_PIL:
            return None

        if size is None:
            size = FilePreview.THUMB_SIZE

        try:
            if raw_data:
                img = Image.open(io.BytesIO(raw_data))
            elif file_path and os.path.exists(file_path):
                img = Image.open(file_path)
            else:
                return None

            img.thumbnail(size, Image.Resampling.LANCZOS)

            # Convert to RGBA for display
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")

            return img

        except Exception:
            return None

    @staticmethod
    def generate_text_preview(file_path: str = None, raw_data: bytes = None,
                               max_bytes: int = None) -> str:
        """
        Generate a text preview string.
        Returns first N bytes decoded as text.
        """
        if max_bytes is None:
            max_bytes = FilePreview.TEXT_PREVIEW_BYTES

        try:
            if raw_data:
                data = raw_data[:max_bytes]
            elif file_path and os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    data = f.read(max_bytes)
            else:
                return "(No data available)"

            # Try UTF-8, then latin-1
            try:
                text = data.decode("utf-8", errors="replace")
            except Exception:
                text = data.decode("latin-1", errors="replace")

            # Clean up
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            return text

        except Exception as e:
            return f"(Preview error: {e})"

    @staticmethod
    def generate_hex_preview(file_path: str = None, raw_data: bytes = None,
                              max_bytes: int = None) -> str:
        """Generate a hex dump preview string."""
        if max_bytes is None:
            max_bytes = FilePreview.HEX_PREVIEW_BYTES

        try:
            if raw_data:
                data = raw_data[:max_bytes]
            elif file_path and os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    data = f.read(max_bytes)
            else:
                return "(No data available)"

            lines = []
            for i in range(0, len(data), 16):
                row = data[i:i + 16]
                hex_part = " ".join(f"{b:02X}" for b in row)
                ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
                lines.append(f"{i:08X}  {hex_part:<48s}  {ascii_part}")

            return "\n".join(lines)

        except Exception as e:
            return f"(Preview error: {e})"

    @staticmethod
    def read_raw_preview_data(device_path: str, offset: int,
                               size: int, max_read: int = 65536) -> bytes:
        """
        Read raw bytes from a device for preview purposes.
        Reads min(size, max_read) bytes from the given offset.
        """
        read_size = min(size, max_read)
        try:
            fd = os.open(device_path, os.O_RDONLY)
            try:
                os.lseek(fd, offset, os.SEEK_SET)
                data = os.read(fd, read_size)
                return data
            finally:
                os.close(fd)
        except Exception:
            return b""
