"""Tiny thread-safe publish / subscribe bus.

Used to push live detection events and full state snapshots to every
connected dashboard channel (Server-Sent Events), so the frontend teammate
gets real-time updates without polling.
"""

import json
import queue
import threading


class EventBus:

    def __init__(self):
        self._subscribers = []
        self._lock = threading.Lock()
        self._latest_event = None
        self._latest_state = None

    # ------------------------------------------------------------
    # Subscribers
    # ------------------------------------------------------------

    def subscribe(self):
        """Return a subscriber queue (call queue.get_nowait() to read)."""
        channel = queue.Queue(maxsize=1000)

        with self._lock:
            self._subscribers.append(channel)

        return channel

    def unsubscribe(self, channel):
        with self._lock:
            try:
                self._subscribers.remove(channel)
            except ValueError:
                pass

    def subscriber_count(self):
        with self._lock:
            return len(self._subscribers)

    # ------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------

    def publish_event(self, row):
        """Announce a newly stored event (a DataEngine row dict)."""
        self._latest_event = row
        self._broadcast({"kind": "event", **row})

    def publish_state(self, snapshot):
        """Announce the latest full sensor / pipeline snapshot."""
        self._latest_state = snapshot
        self._broadcast({"kind": "state", **snapshot})

    # ------------------------------------------------------------
    # Latest values (for new subscribers / /api/events/latest)
    # ------------------------------------------------------------

    def latest_event(self):
        return self._latest_event

    def latest_state(self):
        return self._latest_state

    # ------------------------------------------------------------

    def _broadcast(self, payload):
        message = json.dumps(payload, default=str)

        with self._lock:
            subscribers = list(self._subscribers)

        for channel in subscribers:
            try:
                channel.put_nowait(message)
            except queue.Full:
                try:
                    channel.get_nowait()  # drop oldest
                    channel.put_nowait(message)
                except Exception:
                    pass
            except Exception:
                pass