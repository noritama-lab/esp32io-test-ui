import unittest

from esp32_worker import ESP32Worker


class _SnapshotOnlyESP:
    def __init__(self):
        self.calls = []

    def get_io_state(self):
        self.calls.append("get_io_state")
        return {
            "dio_in": [0, 1, 0, 1, 0, 1],
            "dio_out": [0, 0, 0, 0, 0, 0],
            "adc": [1111, 2222],
            "pwm": [0, 0],
        }

    def read_di(self, pin_id):
        raise AssertionError(f"read_di should not be used for refresh snapshot: {pin_id}")

    def read_adc(self, pin_id):
        raise AssertionError(f"read_adc should not be used for refresh snapshot: {pin_id}")


class ESP32WorkerRefreshTests(unittest.TestCase):
    def test_do_refresh_prefers_atomic_io_snapshot(self):
        worker = ESP32Worker()
        worker.esp = _SnapshotOnlyESP()

        captured = []
        worker.di_adc_updated.connect(lambda di, adc, elapsed: captured.append((di, adc, elapsed)))

        worker.do_refresh()

        self.assertEqual(worker.esp.calls, ["get_io_state"])
        self.assertEqual(len(captured), 1)
        di_values, adc_values, elapsed_ms = captured[0]
        self.assertEqual(di_values, [0, 1, 0, 1, 0, 1])
        self.assertEqual(adc_values, [1111, 2222])
        self.assertGreaterEqual(elapsed_ms, 0.0)


if __name__ == "__main__":
    unittest.main()
