#!/usr/bin/env python3
"""
File Resurrector
A file recovery tool for corrupted drives.

Usage:
    python main.py
    sudo python main.py   (for raw device scanning)
"""

import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.app import App


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
