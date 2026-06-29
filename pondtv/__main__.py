"""PondTV entrypoint: wire everything up and run.

    sudo python3 -m pondtv

Needs privileges to mount the USB and read the keyboard, and the console tty
free so mpv can grab DRM/KMS (stop ``getty@tty1`` first, or run from the
systemd service which does this for you).
"""

from __future__ import annotations

from .manager import Manager


def main() -> None:
    mgr = Manager()
    mgr.start()
    mgr.run_forever()


if __name__ == "__main__":
    main()
