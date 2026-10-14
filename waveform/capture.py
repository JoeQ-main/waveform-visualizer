"""System-audio (WASAPI loopback) capture into a multi-channel ring buffer."""
from __future__ import annotations

import threading

import numpy as np


class RingBuffer:
    """Fixed-size float32 ring buffer of (frames, channels). One writer, many readers."""

    def __init__(self, size: int, channels: int = 1):
        if size <= 0 or channels <= 0:
            raise ValueError("size and channels must be positive")
        self._buf = np.zeros((size, channels), dtype=np.float32)
        self._pos = 0  # next write index
        self._lock = threading.Lock()

    @property
    def size(self) -> int:
        return self._buf.shape[0]

    @property
    def channels(self) -> int:
        return self._buf.shape[1]

    def write(self, frames) -> None:
        frames = np.asarray(frames, dtype=np.float32).reshape(-1, self.channels)
        n = len(frames)
        if n == 0:
            return
        if n >= self.size:  # keep only the newest `size` frames
            frames = frames[-self.size:]
            n = self.size
        with self._lock:
            end = self._pos + n
            if end <= self.size:
                self._buf[self._pos:end] = frames
            else:
                first = self.size - self._pos
                self._buf[self._pos:] = frames[:first]
                self._buf[: n - first] = frames[first:]
            self._pos = end % self.size

    def latest(self, n: int) -> np.ndarray:
        """Return a copy of the newest `n` frames as (n, channels), oldest first."""
        n = max(0, min(n, self.size))
        with self._lock:
            start = (self._pos - n) % self.size
            if start + n <= self.size:
                return self._buf[start : start + n].copy()
            return np.concatenate((self._buf[start:], self._buf[: (start + n) % self.size]))


def deinterleave(interleaved: np.ndarray, channels: int) -> np.ndarray:
    """Reshape interleaved samples to (frames, channels), dropping any partial frame."""
    channels = max(1, channels)
    frames = len(interleaved) // channels
    return np.asarray(interleaved, dtype=np.float32)[: frames * channels].reshape(frames, channels)


def downmix_to_mono(frames: np.ndarray) -> np.ndarray:
    """Average a (frames, channels) array down to one channel."""
    frames = np.asarray(frames, dtype=np.float32)
    if frames.ndim == 1:
        return frames
    return frames.mean(axis=1, dtype=np.float32)


class LoopbackCapture:
    """Captures the default output device via WASAPI loopback into a RingBuffer."""

    def __init__(self, buffer_seconds: float = 0.5, frames_per_buffer: int = 512):
        import pyaudiowpatch as pa  # imported lazily so unit tests do not need audio

        self._pa_mod = pa
        self._pa = pa.PyAudio()
        self._frames_per_buffer = frames_per_buffer
        self._buffer_seconds = buffer_seconds
        self._stream = None
        self._device = None
        self.sample_rate = 48000
        self.channels = 2
        self.buffer = RingBuffer(int(self.sample_rate * buffer_seconds), self.channels)

    # -- device discovery -------------------------------------------------
    def find_default_loopback(self) -> dict:
        pa = self._pa_mod
        try:
            return self._pa.get_default_wasapi_loopback()
        except Exception:
            pass
        wasapi = self._pa.get_host_api_info_by_type(pa.paWASAPI)
        default_out = self._pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
        if default_out.get("isLoopbackDevice"):
            return default_out
        for lb in self._pa.get_loopback_device_info_generator():
            if default_out["name"] in lb["name"]:
                return lb
        raise RuntimeError("No WASAPI loopback device found for the default output")

    @property
    def device_name(self) -> str:
        if not self._device:
            return "(no device)"
        return self._device["name"].replace(" [Loopback]", "")

    # -- stream control ---------------------------------------------------
    def start(self) -> None:
        self.stop()
        pa = self._pa_mod
        dev = self.find_default_loopback()
        self.sample_rate = int(dev["defaultSampleRate"])
        self.channels = max(1, int(dev["maxInputChannels"]))
        self.buffer = RingBuffer(int(self.sample_rate * self._buffer_seconds), self.channels)
        self._device = dev

        def callback(in_data, frame_count, time_info, status):
            data = np.frombuffer(in_data, dtype=np.float32)
            self.buffer.write(deinterleave(data, self.channels))
            return (None, pa.paContinue)

        self._stream = self._pa.open(
            format=pa.paFloat32,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            input_device_index=dev["index"],
            frames_per_buffer=self._frames_per_buffer,
            stream_callback=callback,
        )

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def is_running(self) -> bool:
        try:
            return self._stream is not None and self._stream.is_active()
        except Exception:
            return False

    def default_device_changed(self) -> bool:
        """True if the default output device is no longer the one we capture."""
        try:
            current = self.find_default_loopback()
        except Exception:
            return False
        return self._device is None or current["index"] != self._device["index"]

    def close(self) -> None:
        self.stop()
        try:
            self._pa.terminate()
        except Exception:
            pass
