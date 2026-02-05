# Navidisc – Developer Specification

## 1. Project Overview

**Navidisc** is a Linux-based automation tool that converts Navidrome (Subsonic) playlists into one or more physical CDs (data or audio), handling playlist resolution, file staging, disc capacity planning, burning, and user interaction.

The project is designed to:

* Run on Linux hosts with optical drives
* Interface with Navidrome via the Subsonic API
* Support local and remote music sources
* Automate multi-disc workflows
* Provide both interactive and headless modes
* Be friendly to AI-assisted development and extension

---

## 2. Goals and Non-Goals

### Goals

* Deterministic, repeatable disc creation from playlists
* Minimal manual steps during burning
* Clear, debuggable state transitions
* Strong separation between planning, staging, and burning
* Scriptable and automatable
* Safe defaults (no accidental overwrites or burns)

### Non-Goals

* Acting as a music player
* Managing Navidrome libraries
* Cross-platform disc burning (Linux only for v1)
* DRM or proprietary format handling

---

## 3. Target Environment

### Host OS

* Linux (kernel with optical drive support)
* Tested distros: Debian/Ubuntu, Arch, Fedora

### Required System Tools

* `growisofs` (data CDs)
* `cdrecord` or `cdrdao` (audio CDs, optional)
* `eject`
* `lsblk` or `udevadm`

### Runtime

* Python 3.11+
* Run on host (not inside Navidrome container)

---

## 4. High-Level Architecture

```
┌────────────┐
│   UI/TUI   │  ← CLI, prompts, progress, logs
└─────┬──────┘
      │
┌─────▼──────┐
│ Orchestrator│  ← state machine
└─────┬──────┘
      │
 ┌────▼─────┐   ┌───────────┐   ┌──────────┐
 │ Subsonic │   │ Disc Plan │   │  Burner  │
 │  Client  │   │  Engine   │   │  Adapter │
 └────┬─────┘   └────┬──────┘   └────┬─────┘
      │              │               │
 ┌────▼─────┐   ┌────▼─────┐   ┌─────▼─────┐
 │ Downloader│   │ Staging  │   │ System CD │
 │ /Resolver │   │ Manager  │   │ Utilities │
 └──────────┘   └──────────┘   └───────────┘
```

---

## 5. Core Modules

### 5.1 Subsonic Client (`navidisc.api`)

**Responsibilities**

* Authenticate with Navidrome
* Fetch playlists
* Resolve tracks and metadata
* Provide stream/download URLs

**Key abstractions**

* Playlist
* Track
* Artist
* Album

**Outputs**

* Ordered list of tracks with:
  * ID
  * duration
  * bitrate
  * size (if known)
  * stream URL
  * original path (if resolvable)

---

### 5.2 Track Resolver & Downloader (`navidisc.media`)

**Responsibilities**

* Determine best way to obtain each track:
  1. Local filesystem path
  2. Remote Subsonic download
* Normalize formats if required (optional)
* Verify integrity (size/hash)

**Modes**

* `local-only`
* `download-if-missing`
* `download-always`

**AI-compatibility**

* Pure functions where possible
* Side effects isolated
* Deterministic inputs/outputs

---

### 5.3 Disc Planning Engine (`navidisc.planner`)

**Responsibilities**

* Split playlists into disc-sized sets
* Preserve track order
* Support multiple strategies

**Disc types**

* Data CD (size-based, default 700MB)
* Audio CD (duration-based, default 80 min)

**Planning strategies**

* Greedy sequential (default)
* Duration-optimized (future)
* Fixed track count (future)

**Output (serializable)**

```json
{
  "disc_1": ["track_id_1", "track_id_2"],
  "disc_2": ["track_id_3"]
}
```

---

### 5.4 Staging Manager (`navidisc.staging`)

**Responsibilities**

* Create temporary disc directories
* Copy or hard-link files
* Apply filename normalization
* Optional track renumbering

**Directory structure**

```
staging/
├── disc_01/
│   ├── 01 - Artist - Track.flac
│   └── 02 - Artist - Track.flac
├── disc_02/
```

---

### 5.5 Burner Adapter (`navidisc.burner`)

**Responsibilities**

* Abstract disc burning commands
* Detect drive readiness
* Execute burn commands
* Verify completion

**Backends**

* `growisofs` (data)
* `cdrecord` / `cdrdao` (audio)

**Contract**

```python
burn(disc_path, device) -> BurnResult
```

No UI logic here — pure execution + status.

---

### 5.6 Orchestrator / State Machine (`navidisc.core`)

**Responsibilities**

* Coordinate the full workflow
* Handle retries, failures, aborts
* Drive multi-disc prompting logic

**States**

* INIT
* AUTHENTICATED
* PLAYLIST_RESOLVED
* PLANNED
* STAGING_DISC_N
* WAIT_FOR_DISC
* BURNING_DISC_N
* VERIFYING
* COMPLETE
* ERROR

This explicit state model is **AI-friendly** and debuggable.

---

### 5.7 UI Layer (`navidisc.ui`)

**Modes**

* Interactive CLI (default)
* Non-interactive / batch
* Future: TUI or Web UI

**Responsibilities**

* Display progress
* Prompt user for disc insertion
* Show errors clearly
* Never contain business logic

**Libraries**

* `rich` or `textual`

---

## 6. Configuration System

### File-based (YAML or TOML)

```yaml
navidrome:
  url: http://localhost:4533
  username: user
  password: pass

burning:
  device: /dev/sr0
  disc_type: data
  disc_size_mb: 700

media:
  staging_dir: /tmp/navidisc
  download_mode: download-if-missing
```

### Requirements

* Fully declarative
* Schema-validated
* Serializable for AI generation/editing

---

## 7. CLI Interface

```bash
navidisc burn playlist "Road Trip"
navidisc burn playlist --id 123 --disc-type audio
navidisc plan playlist "Road Trip" --dry-run
```

**Flags**

* `--dry-run`
* `--headless`
* `--force`
* `--output-plan`

---

## 8. Error Handling & Recovery

* Every step returns structured results
* Errors must include:
  * Stage
  * Cause
  * Suggested action
* Partial progress is resumable where possible

---

## 9. Logging & Observability

* Structured logs (JSON optional)
* Verbosity levels
* Session IDs
* Disc IDs

Logs must be machine-parseable for AI tools.

---

## 10. AI Compatibility Principles

This project is designed so that:

* Each module can be reasoned about independently
* Inputs/outputs are serializable
* State transitions are explicit
* Config is machine-editable
* Side effects are isolated
* Determinism is preferred over heuristics

This enables:

* AI-generated plugins
* AI-assisted debugging
* AI-generated test cases
* AI-driven UI layers

---

## 11. Testing Strategy

* Unit tests for planner and resolver
* Mock Subsonic API
* Dry-run burner backend
* Golden-file tests for disc plans

---

## 12. Future Extensions

* DVD / Blu-ray support
* USB image export
* Web UI
* Metadata-aware filename strategies
* Plugin system for planners and burners

---

## 13. License Recommendation

* **GPLv3** (aligns with Navidrome ethos)
* or **Apache 2.0** for broader adoption
