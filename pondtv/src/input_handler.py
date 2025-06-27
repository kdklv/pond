import threading
import queue
from pynput import keyboard
from .utils import log

class InputHandler(threading.Thread):
    """Handles global keyboard input in a separate thread."""

    def __init__(self, action_queue: queue.Queue):
        """
        Initializes the InputHandler.

        Args:
            action_queue: A queue to put actions into for the main thread.
        """
        super().__init__(daemon=True, name="InputHandler")
        self.action_queue = action_queue
        self.log = log
        self._listener = None

        # Define key mappings
        self.key_map = {
            keyboard.Key.space: 'toggle_pause',
            keyboard.Key.right: 'next',
            keyboard.Key.left: 'previous',
            keyboard.Key.up: 'volume_up',
            keyboard.Key.down: 'volume_down',
            keyboard.Key.backspace: 'restart',
            keyboard.Key.esc: 'shutdown',
            's': 'mark_seen',
            'm': 'toggle_mute',
            'i': 'show_guide',
            'p': 'show_guide',
        }

    def on_press(self, key):
        """Callback for when a key is pressed."""
        action = None
        try:
            # Handle special keys
            if key in self.key_map:
                action = self.key_map[key]
            # Handle character keys
            elif hasattr(key, 'char') and key.char in self.key_map:
                action = self.key_map[key.char]
        except Exception as e:
            self.log.error(f"Error processing key press: {e}")

        if action:
            self.log.info(f"Input action detected: '{action}'")
            self.action_queue.put(action)

            # Special case for shutdown to stop the listener thread
            if action == 'shutdown':
                self.log.info("Shutdown key pressed, stopping input listener.")
                self.stop()

    def run(self):
        """Starts the keyboard listener."""
        self.log.info("Starting input handler thread...")
        self._listener = keyboard.Listener(on_press=self.on_press)
        self._listener.start()
        self._listener.join()
        self.log.info("Input handler thread stopped.")

    def stop(self):
        """Stops the keyboard listener."""
        if self._listener and self._listener.running:
            self.log.info("Stopping input listener from main thread.")
            self._listener.stop()

if __name__ == '__main__':
    # Test script for the InputHandler
    log.info("--- Running InputHandler Test ---")
    log.info("Press keys (space, arrows, s, m, esc) to see actions.")
    log.info("Press 'ESC' to exit the test.")
    
    q = queue.Queue()
    handler = InputHandler(q)
    handler.start()

    try:
        while handler.is_alive():
            try:
                action = q.get(timeout=1)
                log.info(f"Action received from queue: {action}")
                if action == 'shutdown':
                    break
            except queue.Empty:
                pass
    except KeyboardInterrupt:
        handler.stop()

    handler.join()
    log.info("--- Test Complete ---") 