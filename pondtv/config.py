"""Runtime configuration: built-in defaults, optional global file, per-drive overrides.

PondTV runs with sane defaults and no config at all. Two optional YAML files tune
it, lowest-to-highest precedence:

1. **built-in defaults** (this module),
2. a **global** ``config.yml`` (``/etc/pondtv/config.yml`` or
   ``~/.config/pondtv/config.yml``) — machine-wide policy, e.g. the deployed
   appliance sets ``allow_quit: false`` so Esc/Q can't drop a guest to a black
   screen,
3. a **per-drive** ``.pondtv/config.yml`` at the USB root — travels with the
   mixtape, so a given drive can default to trailer mode, a different scrub step,
   etc.

Unknown keys are ignored (forward-compatible); a missing or malformed file falls
back to the lower layer rather than crashing — same tolerance as state loading.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any

try:  # pyyaml is a runtime dep, but stay importable (and testable) without it.
    import yaml
except ImportError:  # pragma: no cover - exercised only on a broken install
    yaml = None  # type: ignore[assignment]

# Search path for the optional machine-wide config, first hit wins.
GLOBAL_CONFIG_PATHS = (
    "/etc/pondtv/config.yml",
    os.path.expanduser("~/.config/pondtv/config.yml"),
)
# Per-drive config lives beside state, under the USB root.
DRIVE_CONFIG_REL = ".pondtv/config.yml"


@dataclass(frozen=True)
class Config:
    """Resolved settings. Field defaults are the built-in baseline."""

    mountpoint: str = "/mnt/pondtv"
    poll_interval: float = 2.0          # drive presence poll, seconds
    seek_seconds: float = 10.0          # ←/→ scrub step
    checkpoint_seconds: float = 30.0    # periodic position save while playing
    resume_min_seconds: float = 60.0    # min watched before a video "has a resume point"
    watchdog_seconds: float = 3.0       # mpv liveness check / reconnect cadence
    keyboard_rescan_seconds: float = 3.0  # poll /dev/input for a hot-plugged keyboard
    trailer_default: bool = False       # start in trailer (flip-through) mode
    allow_quit: bool = True             # honour the QUIT action (Esc/Q) — off for kiosks

    def merged(self, overrides: dict[str, Any]) -> "Config":
        """Return a copy with recognised keys from ``overrides`` applied."""
        known = {f.name for f in fields(self)}
        clean = {k: v for k, v in overrides.items() if k in known and v is not None}
        return replace(self, **clean) if clean else self


def _load_yaml(path: str | Path) -> dict[str, Any]:
    """Parse a YAML mapping, or {} on missing/broken/non-mapping file."""
    if yaml is None:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, ValueError):  # missing, unreadable, or malformed YAML
        return {}
    except yaml.YAMLError:  # type: ignore[attr-defined]
        return {}
    return data if isinstance(data, dict) else {}


def _env_overrides() -> dict[str, Any]:
    """A couple of env knobs for the systemd unit, e.g. PONDTV_ALLOW_QUIT=0."""
    out: dict[str, Any] = {}
    val = os.environ.get("PONDTV_ALLOW_QUIT")
    if val is not None:
        out["allow_quit"] = val.strip().lower() not in ("0", "false", "no", "")
    mp = os.environ.get("PONDTV_MOUNTPOINT")
    if mp:
        out["mountpoint"] = mp
    return out


def load_config() -> Config:
    """Built-in defaults ← global file ← environment. (Per-drive layer is applied
    later via :meth:`Config.merged` once a USB root is known.)"""
    cfg = Config()
    for path in GLOBAL_CONFIG_PATHS:
        if os.path.exists(path):
            cfg = cfg.merged(_load_yaml(path))
            break
    return cfg.merged(_env_overrides())


def load_drive_overrides(usb_root: str | Path) -> dict[str, Any]:
    """Read a drive's ``.pondtv/config.yml`` overrides (empty if none)."""
    return _load_yaml(Path(usb_root) / DRIVE_CONFIG_REL)
