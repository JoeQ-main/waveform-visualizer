import unittest

import numpy as np

from waveform.spectrum import SpectrumAnalyzer, MIN_DB


class SpectrumTests(unittest.TestCase):
    def _tone(self, sr, freq, amp=1.0, n=4096):
        t = np.arange(n) / sr
        return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)

    def test_tone_lands_in_the_right_band_near_0_dbfs(self):
        sr = 48000
        an = SpectrumAnalyzer(sr, bands=48)
        db = an.band_db(self._tone(sr, 1000.0))
        peak = int(np.argmax(db))
        self.assertAlmostEqual(db[peak], 0.0, delta=1.0)
        # Band edges are log spaced 30 Hz..20 kHz: 1 kHz sits a bit past the middle.
        edges = np.logspace(np.log10(30), np.log10(20000), 49)
        self.assertTrue(edges[peak] <= 1000.0 < edges[peak + 1])

    def test_silence_is_floor(self):
        an = SpectrumAnalyzer(48000)
        levels = an.update(np.zeros(4096, dtype=np.float32))
        np.testing.assert_array_equal(levels, 0.0)
        self.assertTrue(np.all(an.band_db(np.zeros(4096)) <= MIN_DB))

    def test_levels_release_slowly_after_a_burst(self):
        sr = 48000
        an = SpectrumAnalyzer(sr, decay=0.5)
        hot = an.update(self._tone(sr, 1000.0)).copy()
        cooled = an.update(np.zeros(4096, dtype=np.float32))
        band = int(np.argmax(hot))
        self.assertGreater(hot[band], 0.9)
        self.assertAlmostEqual(cooled[band], hot[band] * 0.5, places=5)

    def test_every_band_has_at_least_one_bin(self):
        an = SpectrumAnalyzer(44100, bands=64)
        self.assertTrue(np.all(an._hi > an._lo))
        self.assertTrue(np.all(np.diff(an._lo) >= 0))


if __name__ == "__main__":
    unittest.main()
