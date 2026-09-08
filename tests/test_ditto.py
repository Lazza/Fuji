import errno
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from acquisition.abstract import Parameters, Report, SparseInfo
from acquisition.ditto import DittoMethod


@unittest.skipUnless(hasattr(os, "mkfifo"), "Requires Unix named pipes")
class DittoMethodTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fuji-ditto-")
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "Test Data"
        self.source.mkdir()
        self.fifo = self.source / "pickup"
        os.mkfifo(self.fifo)
        self.method = DittoMethod()
        self.params = Parameters(source=self.source)
        self.report = Report(self.params, self.method)
        self.image = SparseInfo(
            Path(self.temp.name) / "test.sparseimage",
            "/dev/disk-test",
            "/dev/disk-test-s1",
            str(Path(self.temp.name) / "Test Copy"),
        )
        self.method._initialize_report = Mock(return_value=self.report)
        self.method._create_temporary_image = Mock(return_value=self.image)
        self.method._run_status = Mock(return_value=0)
        self.method._pack_and_hash = Mock(return_value=self.report)

    def assert_guard_active(self):
        # A nonblocking writer only opens successfully while a reader exists.
        fd = os.open(self.fifo, os.O_WRONLY | os.O_NONBLOCK)
        os.close(fd)

    def assert_no_peer(self, fifo):
        with self.assertRaises(OSError) as error:
            fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
            os.close(fd)
        self.assertEqual(error.exception.errno, errno.ENXIO)

    def test_guard_covers_copy_and_closes_before_packaging(self):
        def copy(arguments):
            self.assert_guard_active()
            self.assertEqual(arguments, [
                "ditto", "-X", "-V", f"{self.source}/", self.image.mount
            ])
            return 0

        def package(report):
            self.assert_no_peer(self.fifo)
            self.assertIs(report, self.report)
            return report

        self.method._run_status.side_effect = copy
        self.method._pack_and_hash.side_effect = package
        self.assertIs(self.method.execute(self.params), self.report)
        self.method._run_status.assert_called_once()
        self.method._pack_and_hash.assert_called_once_with(self.report)

    def test_setup_failure_closes_pipes_and_prevents_copy_and_packaging(self):
        second = self.source / "qmgr"
        os.mkfifo(second)
        real_open = os.open
        count = 0

        def fail_second(path, flags):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError(errno.EMFILE, "Too many open files")
            return real_open(path, flags)

        with patch("shared.fifos.os.open", side_effect=fail_second):
            with self.assertRaises(OSError) as error:
                self.method.execute(self.params)
        self.assertEqual(error.exception.errno, errno.EMFILE)
        self.method._run_status.assert_not_called()
        self.method._pack_and_hash.assert_not_called()
        self.assert_no_peer(self.fifo)
        self.assert_no_peer(second)

    def test_copy_exception_closes_pipes_and_prevents_packaging(self):
        def fail_copy(arguments):
            self.assert_guard_active()
            raise RuntimeError("copy failed")

        self.method._run_status.side_effect = fail_copy
        with self.assertRaisesRegex(RuntimeError, "copy failed"):
            self.method.execute(self.params)
        self.method._run_status.assert_called_once()
        self.method._pack_and_hash.assert_not_called()
        self.assert_no_peer(self.fifo)

    def test_missing_temporary_image_does_not_guard_copy_or_package(self):
        self.method._create_temporary_image.return_value = None
        with patch("acquisition.ditto.keep_fifos_open") as guard:
            self.assertIs(self.method.execute(self.params), self.report)
        guard.assert_not_called()
        self.method._run_status.assert_not_called()
        self.method._pack_and_hash.assert_not_called()
        self.assert_no_peer(self.fifo)

    def test_ordinary_nonzero_copy_status_still_packages(self):
        self.method._run_status.return_value = 1
        self.assertIs(self.method.execute(self.params), self.report)
        self.method._run_status.assert_called_once()
        self.method._pack_and_hash.assert_called_once_with(self.report)
        self.assert_no_peer(self.fifo)


if __name__ == "__main__":
    unittest.main()
