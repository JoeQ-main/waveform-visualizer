import unittest

import numpy as np

from waveform.capture import RingBuffer, deinterleave, downmix_to_mono


class RingBufferTests(unittest.TestCase):
    def test_latest_returns_newest_samples_in_order(self):
        rb = RingBuffer(5)
        rb.write([1, 2, 3])
        np.testing.assert_array_equal(rb.latest(3)[:, 0], [1, 2, 3])
        rb.write([4, 5, 6, 7])  # wraps around
        np.testing.assert_array_equal(rb.latest(5)[:, 0], [3, 4, 5, 6, 7])

    def test_write_larger_than_buffer_keeps_newest(self):
        rb = RingBuffer(4)
        rb.write(np.arange(10))
        np.testing.assert_array_equal(rb.latest(4)[:, 0], [6, 7, 8, 9])

    def test_latest_clamps_n_and_starts_zeroed(self):
        rb = RingBuffer(3)
        self.assertEqual(rb.latest(10).shape, (3, 1))
        np.testing.assert_array_equal(rb.latest(3)[:, 0], [0, 0, 0])
        self.assertEqual(len(rb.latest(0)), 0)

    def test_stereo_frames_keep_channels_separate(self):
        rb = RingBuffer(3, channels=2)
        rb.write([[1, -1], [2, -2]])
        rb.write([[3, -3], [4, -4]])  # wraps
        out = rb.latest(3)
        np.testing.assert_array_equal(out[:, 0], [2, 3, 4])
        np.testing.assert_array_equal(out[:, 1], [-2, -3, -4])

    def test_rejects_non_positive_size(self):
        with self.assertRaises(ValueError):
            RingBuffer(0)
        with self.assertRaises(ValueError):
            RingBuffer(4, channels=0)


class DeinterleaveAndDownmixTests(unittest.TestCase):
    def test_deinterleave_stereo(self):
        data = np.array([1.0, 0.0, 0.5, 0.5, -1.0, 1.0], dtype=np.float32)
        frames = deinterleave(data, 2)
        self.assertEqual(frames.shape, (3, 2))
        np.testing.assert_allclose(frames[:, 0], [1.0, 0.5, -1.0])
        np.testing.assert_allclose(downmix_to_mono(frames), [0.5, 0.5, 0.0])

    def test_mono_passthrough(self):
        data = np.array([0.1, 0.2], dtype=np.float32)
        np.testing.assert_array_equal(downmix_to_mono(deinterleave(data, 1)), data)

    def test_partial_frame_is_dropped(self):
        data = np.array([1.0, 1.0, 1.0], dtype=np.float32)
        self.assertEqual(deinterleave(data, 2).shape, (1, 2))


if __name__ == "__main__":
    unittest.main()
