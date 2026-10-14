"""Spectrum analysis: FFT of a mono block into log-spaced band levels in dB."""
from __future__ import annotations

import numpy as np

FFT_SIZE = 4096
MIN_DB = -70.0
MAX_DB = 0.0


class SpectrumAnalyzer:
    """Turns a block of mono samples into `bands` smoothed levels in the 0..1 range."""

    def __init__(self, sample_rate: int, bands: int = 48, fft_size: int = FFT_SIZE,
                 f_lo: float = 30.0, f_hi: float = 20000.0, decay: float = 0.85):
        self.sample_rate = sample_rate
        self.bands = bands
        self.fft_size = fft_size
        self.decay = decay
        self._window = np.hanning(fft_size).astype(np.float32)
        self._norm = 2.0 / self._window.sum()  # sinusoid of amplitude A -> |X| = A

        nyquist = sample_rate / 2
        f_hi = min(f_hi, nyquist)
        edges = np.logspace(np.log10(f_lo), np.log10(f_hi), bands + 1)
        freqs = np.fft.rfftfreq(fft_size, 1.0 / sample_rate)
        # For each band find the bin range; make sure every band has at least one bin.
        self._lo = np.searchsorted(freqs, edges[:-1], side="left")
        self._hi = np.searchsorted(freqs, edges[1:], side="left")
        self._hi = np.maximum(self._hi, self._lo + 1)
        self._hi = np.minimum(self._hi, len(freqs))
        self._lo = np.minimum(self._lo, self._hi - 1)
        self.levels = np.zeros(bands, dtype=np.float32)

    def band_db(self, samples: np.ndarray) -> np.ndarray:
        """Instantaneous per-band peak magnitude in dBFS (no smoothing)."""
        x = np.asarray(samples, dtype=np.float32)
        if len(x) < self.fft_size:
            x = np.concatenate((np.zeros(self.fft_size - len(x), dtype=np.float32), x))
        else:
            x = x[-self.fft_size:]
        mag = np.abs(np.fft.rfft(x * self._window)) * self._norm
        out = np.empty(self.bands, dtype=np.float32)
        for i in range(self.bands):
            out[i] = mag[self._lo[i]:self._hi[i]].max()
        return 20.0 * np.log10(out + 1e-9)

    def update(self, samples: np.ndarray) -> np.ndarray:
        """Feed new samples; returns smoothed band levels normalised to 0..1."""
        db = np.clip(self.band_db(samples), MIN_DB, MAX_DB)
        target = (db - MIN_DB) / (MAX_DB - MIN_DB)
        # Instant attack, exponential release.
        self.levels = np.where(target > self.levels, target,
                               self.levels * self.decay + target * (1 - self.decay))
        return self.levels
