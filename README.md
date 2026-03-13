# File Resurrector

A file recovery tool for corrupted drives. Scan and rescue lost files with a user-friendly GUI.

## ⚠️ Disclaimer

> **Use at your own risk.** This tool attempts to recover files from potentially corrupted drives. Always back up important data before attempting recovery. The authors are not responsible for any data loss.

## Features

- 🖥️ **User-Friendly GUI** - Built with Tkinter for intuitive interaction
- 🔍 **Deep Scanning** - Scan drives at the sector level for recoverable files
- 📁 **Multiple Format Support** - Supports recovery of various file types
- 🔄 **Preview Before Recovery** - Preview recoverable files before saving

## Installation

\\\ash
# Clone the repository
git clone https://github.com/bigmrstorm/file-resurector.git
cd file-resurector

# Install dependencies
pip install -r requirements.txt
\\\

## Usage

### Basic Usage
\\\ash
python main.py
\\\

### Advanced (Raw Device Scanning)
\\\ash
sudo python main.py
\\\

> Running with sudo enables raw device scanning for deeper recovery options.

## Requirements

- Python 3.7+
- Tkinter (usually included with Python)
- Admin/sudo privileges (optional, for raw device access)

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## Author

Created by [bigmrstorm](https://github.com/bigmrstorm)