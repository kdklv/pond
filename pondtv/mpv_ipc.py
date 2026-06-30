"""JSON-IPC client for a long-lived mpv process.

mpv exposes a unix socket (``--input-ipc-server=...``) speaking newline-delimited
JSON. We roll our own ~thin client rather than depending on python-mpv/libmpv-dev
so there's no version coupling — see docs/PLAN.md.

Protocol (https://mpv.io/manual/stable/#json-ipc):

* We send ``{"command": [...], "request_id": N}\n``.
* mpv replies ``{"error": "success", "data": ..., "request_id": N}\n`` for that id.
* Asynchronous events arrive unsolicited as ``{"event": "..."}\n`` (e.g. end-file,
  property-change). A background reader thread demuxes the two.

Usage::

    proc = launch_mpv(SOCKET_PATH)            # one long-lived idle mpv
    mpv = MpvIPC(SOCKET_PATH); mpv.connect()
    mpv.on_event(lambda e: print(e))
    mpv.loadfile("/path/to/video.mkv")
    mpv.set_pause(False)
    pos = mpv.get_property("time-pos")
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from typing import Any, Callable

# Default control socket. Lives in /tmp (tmpfs) so it never touches the USB or
# the read-only root, and is recreated by mpv on every launch.
DEFAULT_SOCKET = "/tmp/pondtv-mpv.sock"

# Args for the one long-lived mpv. DRM/KMS, no window, idle so it survives with
# no file loaded, keep-open so a finished file holds rather than quitting mpv.
MPV_ARGS = [
    "--idle=yes",
    "--force-window=no",
    "--vo=gpu",
    "--gpu-context=drm",
    "--hwdec=auto",
    "--sub-auto=fuzzy",
    "--keep-open=yes",
    "--no-config",
    "--no-terminal",
    # Never write watch-later/resume state to the (read-only) root: --no-config
    # ignores config files but not the resume machinery, so disable it outright
    # and divert any residual writes to tmpfs.
    "--no-resume-playback",
    "--watch-later-directory=/tmp/pondtv-watch-later",
]


class MpvError(RuntimeError):
    """An mpv command returned an error other than ``success``."""


class MpvIPC:
    """Thread-safe client for one mpv control socket."""

    def __init__(self, socket_path: str = DEFAULT_SOCKET):
        self.socket_path = socket_path
        self._sock: socket.socket | None = None
        self._send_lock = threading.Lock()
        self._req_id = 0
        self._responses: dict[int, dict] = {}
        self._awaited: set[int] = set()  # request ids someone is blocking on
        self._cond = threading.Condition()
        self._event_handlers: list[Callable[[dict], None]] = []
        self._reader: threading.Thread | None = None
        self._running = False

    # -- connection -------------------------------------------------------

    def connect(self, timeout: float = 10.0) -> None:
        """Connect to the socket, retrying until mpv has created it."""
        deadline = time.time() + timeout
        last_err: Exception | None = None
        while time.time() < deadline:
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(self.socket_path)
                self._sock = s
                break
            except (FileNotFoundError, ConnectionRefusedError, OSError) as e:
                last_err = e
                time.sleep(0.1)
        else:
            raise TimeoutError(
                f"could not connect to mpv socket {self.socket_path!r}: {last_err}"
            )
        self._running = True
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def close(self) -> None:
        self._running = False
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def is_connected(self) -> bool:
        """True while the socket is open and the reader thread is alive.

        Flips false when mpv dies (the reader sees the socket close); the manager
        polls this to drive its watchdog/reconnect.
        """
        return self._running and self._sock is not None

    # -- background reader ------------------------------------------------

    def _read_loop(self) -> None:
        buf = b""
        while self._running and self._sock is not None:
            try:
                data = self._sock.recv(65536)
            except OSError:
                break
            if not data:
                break  # mpv closed the socket (likely died)
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._dispatch(msg)
        self._running = False
        # Wake any callers blocked waiting on a response.
        with self._cond:
            self._cond.notify_all()

    def _dispatch(self, msg: dict) -> None:
        if "event" in msg:
            for handler in list(self._event_handlers):
                try:
                    handler(msg)
                except Exception:  # noqa: BLE001 - a bad handler must not kill the reader
                    pass
        elif "request_id" in msg:
            with self._cond:
                # Only keep replies someone is actually waiting on; fire-and-forget
                # (command_async) replies are dropped so the dict can't grow.
                if msg["request_id"] in self._awaited:
                    self._responses[msg["request_id"]] = msg
                    self._cond.notify_all()

    # -- commands ---------------------------------------------------------

    def command(self, *args: Any, timeout: float = 5.0) -> Any:
        """Send a command and block for its matching reply; return ``data``."""
        if not self._running or self._sock is None:
            raise ConnectionError("not connected to mpv")
        with self._send_lock:
            self._req_id += 1
            rid = self._req_id
        with self._cond:
            self._awaited.add(rid)
        payload = (json.dumps({"command": list(args), "request_id": rid}) + "\n").encode()
        self._sock.sendall(payload)

        deadline = time.time() + timeout
        with self._cond:
            while rid not in self._responses:
                if not self._running:
                    raise ConnectionError("connection to mpv lost")
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise TimeoutError(f"timed out waiting for reply to {args!r}")
                self._cond.wait(remaining)
            resp = self._responses.pop(rid)
            self._awaited.discard(rid)

        if resp.get("error") != "success":
            raise MpvError(f"{args[0]} failed: {resp.get('error')}")
        return resp.get("data")

    def command_async(self, *args: Any) -> None:
        """Send a command without waiting for the reply.

        Safe to call from the IPC reader thread (e.g. an event handler): a
        blocking :meth:`command` there would deadlock, since the reply can only
        be read by that same thread. We don't need the result for fire-and-forget
        actions like a post-load seek.
        """
        if not self._running or self._sock is None:
            return
        with self._send_lock:
            self._req_id += 1
            rid = self._req_id
        payload = (json.dumps({"command": list(args), "request_id": rid}) + "\n").encode()
        try:
            self._sock.sendall(payload)
        except OSError:
            pass

    # -- convenience wrappers --------------------------------------------

    def loadfile(self, path: str, mode: str = "replace") -> None:
        self.command("loadfile", path, mode)

    def get_property(self, name: str) -> Any:
        return self.command("get_property", name)

    def set_property(self, name: str, value: Any) -> None:
        self.command("set_property", name, value)

    def set_property_async(self, name: str, value: Any) -> None:
        """Fire-and-forget property set — safe to call while holding a lock or
        from the reader thread, unlike the blocking :meth:`set_property`."""
        self.command_async("set_property", name, value)

    def set_pause(self, paused: bool) -> None:
        self.set_property("pause", paused)

    def seek_absolute(self, seconds: float) -> None:
        self.command("seek", seconds, "absolute")

    def restart(self) -> None:
        self.seek_absolute(0)

    def show_text(self, text: str, duration_ms: int = 2000) -> None:
        self.command("show-text", text, duration_ms)

    def observe_property(self, name: str, obs_id: int = 1) -> None:
        self.command("observe_property", obs_id, name)

    def on_event(self, handler: Callable[[dict], None]) -> None:
        """Register a callback for asynchronous events (end-file, etc.)."""
        self._event_handlers.append(handler)


def launch_mpv(
    socket_path: str = DEFAULT_SOCKET, extra_args: list[str] | None = None
) -> subprocess.Popen:
    """Start one long-lived idle mpv bound to ``socket_path``."""
    # A stale socket file from a previous run would block mpv from binding.
    try:
        os.unlink(socket_path)
    except FileNotFoundError:
        pass
    args = ["mpv", *MPV_ARGS, f"--input-ipc-server={socket_path}", *(extra_args or [])]
    return subprocess.Popen(args)


if __name__ == "__main__":
    # Step-2 smoke demo: launch idle mpv, drive it over the socket, prove we can
    # load/pause/seek, read playback position, and catch end-of-file.
    #   python3 -m pondtv.mpv_ipc /path/to/test.mp4
    import sys

    if len(sys.argv) < 2:
        print("usage: python3 -m pondtv.mpv_ipc <video-file>")
        sys.exit(1)
    video = sys.argv[1]

    print("launching idle mpv ...")
    proc = launch_mpv()
    try:
        mpv = MpvIPC()
        mpv.connect()
        print("connected to socket")

        eof = threading.Event()

        def on_event(e: dict) -> None:
            print("  [event]", e.get("event"), {k: v for k, v in e.items() if k != "event"})
            # With --keep-open=yes mpv holds the last frame at EOF instead of
            # emitting end-file, so the reliable end signal is the eof-reached
            # property flipping true. We watch both.
            if e.get("event") == "end-file":
                eof.set()
            if e.get("event") == "property-change" and e.get("name") == "eof-reached" and e.get("data"):
                eof.set()

        mpv.on_event(on_event)

        print(f"loadfile {video}")
        mpv.loadfile(video)
        mpv.observe_property("eof-reached", 1)
        mpv.set_pause(False)

        # Give mpv a moment to demux, then read back playback state.
        time.sleep(1.5)
        print("  duration  =", mpv.get_property("duration"))
        print("  time-pos  =", mpv.get_property("time-pos"))
        print("  percent   =", mpv.get_property("percent-pos"))

        print("pause for 1s ...")
        mpv.set_pause(True)
        time.sleep(1.0)
        print("  paused    =", mpv.get_property("pause"))
        mpv.set_pause(False)

        print("seek to 5s ...")
        mpv.seek_absolute(5)
        time.sleep(0.5)
        print("  time-pos  =", mpv.get_property("time-pos"))

        mpv.show_text("PondTV IPC OK", 2000)

        print("waiting for end-of-file (max 30s) ...")
        if eof.wait(timeout=30):
            print("got end-file event")
        else:
            print("no end-file within 30s")
    finally:
        print("quitting mpv")
        try:
            mpv.command("quit")
        except Exception:  # noqa: BLE001 - best-effort; we terminate below anyway
            pass
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
