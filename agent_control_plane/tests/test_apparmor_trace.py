from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.summarize_apparmor_trace import executable_from_line


class AppArmorTraceTests(unittest.TestCase):
    def test_extracts_successful_execve(self) -> None:
        line = 'execve("/bin/sh", ["/bin/sh"], 0x0) = 0'
        self.assertEqual(executable_from_line(line), "/bin/sh")

    def test_ignores_failed_lookup(self) -> None:
        line = 'execve("/usr/local/bin/python3", ["python3"], 0x0) = -1 ENOENT'
        self.assertIsNone(executable_from_line(line))

    def test_extracts_execveat(self) -> None:
        line = 'execveat(3, "/usr/bin/python3", ["python3"], 0x0, 0) = 0'
        self.assertEqual(executable_from_line(line), "/usr/bin/python3")


if __name__ == "__main__":
    unittest.main()
