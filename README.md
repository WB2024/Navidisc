# Navidisc

**Convert Navidrome playlists to physical CDs with ease.**

Navidisc is a Linux-based automation tool that takes your Navidrome (Subsonic) playlists and burns them to one or more physical CDs. It handles playlist resolution, file staging, disc capacity planning, and multi-disc workflows automatically.

## Features

- 🎵 **Subsonic API Integration** - Connect directly to Navidrome or any Subsonic-compatible server
- 💿 **Smart Disc Planning** - Automatically splits playlists across multiple discs while preserving track order
- 📀 **Data & Audio CDs** - Support for both data CDs (700MB) and audio CDs (80 min)
- 🔄 **Multi-Disc Workflow** - Guided prompts for disc insertion during multi-disc burns
- ⚡ **Efficient Staging** - Uses hardlinks when possible to minimize disk space
- 🖥️ **Interactive & Headless** - Works interactively or in automated/scripted environments
- 🔧 **Configurable** - YAML-based configuration with sensible defaults

## Requirements

### System
- Linux with optical drive support (kernel with CD/DVD writing capability)
- Tested on: Debian/Ubuntu, Arch, Fedora

### System Tools
- `growisofs` - For data CDs (from `dvd+rw-tools` package)
- `cdrecord` or `cdrdao` - For audio CDs (optional)
- `eject` - For disc ejection
- `lsblk` or `udevadm` - For drive detection

### Python
- Python 3.11 or later

## Installation

### From Source (Development)

```bash
# Clone the repository
git clone https://github.com/navidisc/navidisc.git
cd navidisc

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e ".[dev]"
```

### System Dependencies (Ubuntu/Debian)

```bash
sudo apt install dvd+rw-tools cdrdao wodim eject
```

### System Dependencies (Arch)

```bash
sudo pacman -S dvd+rw-tools cdrdao cdrtools eject
```

### System Dependencies (Fedora)

```bash
sudo dnf install dvd+rw-tools cdrdao wodim eject
```

## Quick Start

### 1. Create Configuration

```bash
# Create config directory
mkdir -p ~/.config/navidisc

# Create configuration file
cat > ~/.config/navidisc/config.yaml << 'EOF'
navidrome:
  url: http://localhost:4533
  username: your_username
  password: your_password

burning:
  device: /dev/sr0
  disc_type: data
  disc_size_mb: 700

media:
  staging_dir: /tmp/navidisc
  download_mode: download-if-missing
EOF
```

### 2. Plan a Burn (Dry Run)

```bash
# See how a playlist would be split across discs
navidisc plan playlist "Road Trip" --dry-run
```

### 3. Burn a Playlist

```bash
# Burn a playlist by name
navidisc burn playlist "Road Trip"

# Burn by playlist ID
navidisc burn playlist --id abc123

# Burn as audio CD
navidisc burn playlist "Road Trip" --disc-type audio
```

## CLI Reference

### Commands

```bash
navidisc burn playlist <name|--id ID>    # Burn a playlist to disc(s)
navidisc plan playlist <name|--id ID>    # Plan without burning
navidisc list playlists                  # List available playlists
navidisc config show                     # Show current configuration
navidisc config init                     # Create example configuration
```

### Global Options

| Option | Description |
|--------|-------------|
| `--config FILE` | Use alternate config file |
| `--dry-run` | Plan only, don't burn |
| `--headless` | Non-interactive mode |
| `--force` | Skip confirmation prompts |
| `--verbose` / `-v` | Increase output verbosity |

### Burn Options

| Option | Description |
|--------|-------------|
| `--disc-type TYPE` | `data` or `audio` |
| `--device PATH` | Optical drive device |
| `--no-verify` | Skip post-burn verification |
| `--no-eject` | Don't eject disc after burn |
| `--output-plan FILE` | Save burn plan to JSON |

## Configuration

Navidisc uses YAML configuration stored at `~/.config/navidisc/config.yaml`.

### Full Configuration Reference

```yaml
navidrome:
  url: http://localhost:4533      # Navidrome server URL
  username: user                  # API username
  password: pass                  # API password

burning:
  device: /dev/sr0                # Optical drive path
  disc_type: data                 # data or audio
  disc_size_mb: 700               # Data disc capacity (MB)
  audio_disc_minutes: 80          # Audio disc capacity (minutes)
  write_speed: null               # null for auto, or specific speed
  verify_after_burn: true         # Verify disc after burning
  eject_after_burn: true          # Eject disc when done

media:
  staging_dir: /tmp/navidisc      # Temp directory for staging
  download_mode: download-if-missing  # local-only, download-if-missing, download-always
  use_hardlinks: true             # Use hardlinks to save space
  normalize_filenames: true       # Clean filenames for disc
  include_track_numbers: true     # Prefix with 01, 02, etc.

logging:
  level: INFO                     # DEBUG, INFO, WARNING, ERROR
  format: text                    # text or json
  file: null                      # Optional log file path
```

## Architecture

Navidisc follows a modular, state-machine-driven architecture:

```
┌────────────┐
│   CLI/UI   │  ← User interaction, progress display
└─────┬──────┘
      │
┌─────▼──────┐
│Orchestrator│  ← State machine coordinating workflow
└─────┬──────┘
      │
 ┌────▼─────┐   ┌───────────┐   ┌──────────┐
 │ Subsonic │   │ Disc Plan │   │  Burner  │
 │  Client  │   │  Engine   │   │  Adapter │
 └────┬─────┘   └────┬──────┘   └────┬─────┘
      │              │               │
 ┌────▼─────┐   ┌────▼─────┐   ┌─────▼─────┐
 │ Media    │   │ Staging  │   │ System CD │
 │ Resolver │   │ Manager  │   │ Utilities │
 └──────────┘   └──────────┘   └───────────┘
```

### Modules

| Module | Description |
|--------|-------------|
| `navidisc.api` | Subsonic API client for Navidrome |
| `navidisc.media` | Track resolution and downloading |
| `navidisc.planner` | Disc capacity planning |
| `navidisc.staging` | File staging and preparation |
| `navidisc.burner` | Disc burning abstraction |
| `navidisc.core` | Orchestrator state machine |
| `navidisc.ui` | CLI and user interaction |
| `navidisc.config` | Configuration management |
| `navidisc.models` | Shared data models |

## Development

### Setup

```bash
# Clone and install in dev mode
git clone https://github.com/navidisc/navidisc.git
cd navidisc
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Running Tests

```bash
pytest
pytest --cov=navidisc  # With coverage
```

### Code Quality

```bash
ruff check .           # Linting
ruff format .          # Formatting
mypy src/navidisc      # Type checking
```

### Project Structure

```
navidisc/
├── docs/
│   └── spec.md            # Detailed specification
├── src/
│   └── navidisc/
│       ├── __init__.py
│       ├── api/           # Subsonic client
│       ├── burner/        # Disc burning
│       ├── cli.py         # CLI entry point
│       ├── config.py      # Configuration
│       ├── core/          # Orchestrator
│       ├── media/         # Media handling
│       ├── models.py      # Data models
│       ├── planner/       # Disc planning
│       ├── staging/       # File staging
│       └── ui/            # User interface
├── tests/
├── pyproject.toml
└── README.md
```

## Workflow States

The orchestrator manages these states:

| State | Description |
|-------|-------------|
| `INIT` | Initial state |
| `AUTHENTICATED` | Connected to Navidrome |
| `PLAYLIST_RESOLVED` | Tracks fetched and resolved |
| `PLANNED` | Disc plan created |
| `STAGING_DISC` | Staging files for current disc |
| `WAIT_FOR_DISC` | Waiting for user to insert disc |
| `BURNING_DISC` | Burning in progress |
| `VERIFYING` | Verifying burned disc |
| `COMPLETE` | All discs burned successfully |
| `ERROR` | Error occurred (see logs) |

## Troubleshooting

### Permission Denied on /dev/sr0

```bash
# Add user to cdrom group
sudo usermod -aG cdrom $USER
# Log out and back in
```

### Drive Not Detected

```bash
# Check for optical drive
lsblk | grep sr
# Or
ls -la /dev/sr*
```

### Disc Capacity Errors

- Ensure correct disc type is selected
- Check `disc_size_mb` in config matches your media
- For audio CDs, check `audio_disc_minutes`

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Navidrome](https://www.navidrome.org/) - The music server that inspired this project
- [Subsonic API](http://www.subsonic.org/pages/api.jsp) - The API specification used for integration

---

**Note:** This project is in active development. Features and APIs may change.
