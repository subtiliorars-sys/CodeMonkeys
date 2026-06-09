#!/usr/bin/env python3
"""
🍌📋 Queue Manager — Prompt Queue and /loop Command System
===========================================================
Provides a PromptQueue singleton for sequential async prompt processing,
and a LoopCommand system for repeating prompts at intervals (like /loop).

Uses only Python stdlib: queue, threading, time, re, uuid.

Processing calls gemini_integration._make_gemini_request (which also
delegates to OpenRouter via openrouter_bridge).
"""

import queue as _queue_mod
import re
import threading
import time
import uuid


# ── PromptQueue ──────────────────────────────────────────────────

class PromptQueue:
    """A FIFO queue for prompt processing with async capability.
    Uses queue.Queue + threading.Thread to process prompts without blocking.
    """

    def __init__(self):
        self.queue = _queue_mod.Queue()
        self.results = {}       # task_id -> result dict
        self._results_lock = threading.Lock()
        self._worker = None
        self._running = False
        self._completed_count = 0
        self._failed_count = 0
        self._active = False

    # ── Public API ──────────────────────────────────────────────

    def enqueue(self, prompt, system_instruction=None, temperature=0.8, max_tokens=200):
        """Add a prompt to the queue. Returns a task_id (UUID string)."""
        task_id = str(uuid.uuid4())
        item = {
            "task_id": task_id,
            "prompt": prompt,
            "system_instruction": system_instruction,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "enqueued_at": time.time(),
        }
        self.queue.put(item)
        return task_id

    def get_result(self, task_id, block=True, timeout=None):
        """Get result for a task_id. If block=True, waits for completion."""
        if not block:
            with self._results_lock:
                return self.results.get(task_id)

        # Blocking: poll until result appears
        deadline = None if timeout is None else time.time() + timeout
        while True:
            with self._results_lock:
                if task_id in self.results:
                    return self.results[task_id]
            if deadline is not None and time.time() >= deadline:
                raise TimeoutError(
                    f"Result for {task_id} not available within timeout"
                )
            time.sleep(0.05)

    def status(self):
        """Return dict: queue_size, active, completed_count, failed_count."""
        return {
            "queue_size": self.queue.qsize(),
            "active": self._active,
            "completed_count": self._completed_count,
            "failed_count": self._failed_count,
        }

    def start(self):
        """Start the worker thread."""
        if self._worker is not None and self._worker.is_alive():
            return
        self._running = True
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def stop(self):
        """Stop the worker thread (graceful — finishes current item)."""
        self._running = False
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=3.0)

    # ── Internal ────────────────────────────────────────────────

    def _worker_loop(self):
        """Background thread that processes queue items sequentially."""
        while self._running:
            try:
                item = self.queue.get(timeout=0.5)
            except _queue_mod.Empty:
                continue

            self._active = True
            try:
                # Lazy import to avoid circular dependency at module level
                from gemini_integration import _make_gemini_request

                result_text = _make_gemini_request(
                    prompt=item["prompt"],
                    system_instruction=item["system_instruction"],
                    temperature=item["temperature"],
                    max_tokens=item["max_tokens"],
                )

                with self._results_lock:
                    self.results[item["task_id"]] = {
                        "status": "completed",
                        "result": result_text,
                        "completed_at": time.time(),
                    }
                self._completed_count += 1
            except Exception as exc:
                with self._results_lock:
                    self.results[item["task_id"]] = {
                        "status": "failed",
                        "error": str(exc),
                        "completed_at": time.time(),
                    }
                self._failed_count += 1
            finally:
                self._active = False
                self.queue.task_done()


# ── LoopCommand ──────────────────────────────────────────────────

class LoopCommand:
    """Implements /loop functionality like Claude Code.
    Usage: /loop 15m "prompt text"
    Repeats feeding the prompt at the given interval.
    Loops run indefinitely until explicitly stopped.
    """

    def __init__(self):
        self._loops = {}       # loop_id -> dict
        self._lock = threading.Lock()

    # ── Public API ──────────────────────────────────────────────

    def start_loop(self, duration_str, prompt, system_instruction=None, temperature=0.8):
        """Start a loop.
        duration_str: "15m", "1h", "30s", etc. (interval between repeats)
        prompt: the prompt to repeat
        Returns loop_id (UUID string).
        """
        interval = parse_duration(duration_str)
        loop_id = str(uuid.uuid4())

        loop_info = {
            "loop_id": loop_id,
            "prompt": prompt,
            "interval": interval,
            "started_at": time.time(),
            "system_instruction": system_instruction,
            "temperature": temperature,
            "timer": None,
            "iteration": 0,
        }

        with self._lock:
            self._loops[loop_id] = loop_info

        # Fire immediately, then schedule next
        self._fire_loop(loop_id)

        return loop_id

    def stop_loop(self, loop_id):
        """Stop a specific loop. Returns True if found and stopped."""
        with self._lock:
            loop = self._loops.pop(loop_id, None)
            if loop and loop["timer"]:
                loop["timer"].cancel()
                return True
        return False

    def stop_all_loops(self):
        """Stop all running loops."""
        with self._lock:
            for loop_id, loop in list(self._loops.items()):
                if loop["timer"]:
                    loop["timer"].cancel()
            self._loops.clear()

    def list_loops(self):
        """Return list of active loops with their status."""
        result = []
        now = time.time()
        with self._lock:
            for loop_id, loop in list(self._loops.items()):
                elapsed = now - loop["started_at"]
                prompt_preview = (
                    loop["prompt"][:80] + "..."
                    if len(loop["prompt"]) > 80
                    else loop["prompt"]
                )
                result.append({
                    "loop_id": loop_id,
                    "prompt": prompt_preview,
                    "interval": loop["interval"],
                    "elapsed": elapsed,
                    "iteration": loop["iteration"],
                })
        return result

    # ── Internal ────────────────────────────────────────────────

    def _schedule_next(self, loop_id):
        """Schedule the next iteration of a loop."""
        with self._lock:
            loop = self._loops.get(loop_id)
            if loop is None:
                return

            timer = threading.Timer(
                loop["interval"], self._fire_loop, args=[loop_id]
            )
            timer.daemon = True
            loop["timer"] = timer
            timer.start()

    def _fire_loop(self, loop_id):
        """Called when a loop timer fires — enqueue the prompt and reschedule."""
        with self._lock:
            loop = self._loops.get(loop_id)
            if loop is None:
                return

            loop["iteration"] += 1

        # Enqueue the prompt via the module-level singleton
        _queue.enqueue(
            prompt=loop["prompt"],
            system_instruction=loop["system_instruction"],
            temperature=loop["temperature"],
        )

        # Schedule the next fire
        self._schedule_next(loop_id)


# ── Parse helpers ───────────────────────────────────────────────

def parse_duration(duration_str):
    """Parse "15m", "1h", "30s", "2h30m" into seconds.

    Args:
        duration_str: Human-readable duration string.

    Returns:
        Total seconds as int.

    Raises:
        ValueError if the string cannot be parsed.
    """
    if not duration_str or not duration_str.strip():
        raise ValueError("Empty duration string")

    duration_str = duration_str.strip().lower()
    total = 0

    # Match groups of number + unit
    pattern = re.compile(r"(\d+)\s*(h|m|s)")
    matches = pattern.findall(duration_str)

    if not matches:
        raise ValueError(
            f"Could not parse duration: '{duration_str}'. "
            "Use format like '15m', '1h', '30s', '2h30m'."
        )

    for value, unit in matches:
        value = int(value)
        if unit == "h":
            total += value * 3600
        elif unit == "m":
            total += value * 60
        elif unit == "s":
            total += value

    if total <= 0:
        raise ValueError(f"Duration must be positive: '{duration_str}'")

    return total


def parse_loop_command(args_str):
    """Parse '/loop 15m "prompt here"' into (duration_seconds, prompt).

    Supports both quoted (single/double) and bare prompts after the duration.

    Args:
        args_str: The full argument string after '/loop', e.g.
                  '15m "tell me a joke"'  or   '30s hello world'

    Returns:
        Tuple of (duration_seconds: int, prompt: str)

    Raises:
        ValueError on invalid format.
    """
    if not args_str or not args_str.strip():
        raise ValueError("Empty loop command — usage: /loop <duration> <prompt>")

    args_str = args_str.strip()

    # Split on first space to separate duration from prompt
    parts = args_str.split(maxsplit=1)
    if len(parts) < 2:
        raise ValueError(
            "Usage: /loop <duration> <prompt>. "
            "Example: /loop 15m 'tell me a joke'"
        )

    duration_str = parts[0]
    prompt_raw = parts[1]

    # Strip matching quotes if present
    prompt = prompt_raw.strip()
    if len(prompt) >= 2 and prompt[0] == prompt[-1] and prompt[0] in ('"', "'"):
        prompt = prompt[1:-1]

    if not prompt:
        raise ValueError("Prompt is empty")

    seconds = parse_duration(duration_str)
    return (seconds, prompt)


# ── Singletons ───────────────────────────────────────────────────

_queue = PromptQueue()          # module-internal reference
_queue.start()

queue = _queue                   # public singleton
loop_command = LoopCommand()     # public singleton


# ── Module-level convenience helpers ─────────────────────────────

def get_queue_status():
    """Convenience: return current queue status dict."""
    return queue.status()


def get_active_loops():
    """Convenience: return list of active loops."""
    return loop_command.list_loops()
