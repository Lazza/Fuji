import errno
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from shared.fifos import keep_fifos_open


@unittest.skipUnless(hasattr(os, "mkfifo"), "Requires Unix named pipes")
class FifoGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fuji-fifo-")
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "source"
        self.source.mkdir()
        self.fifo = self.source / "pickup"
        os.mkfifo(self.fifo, 0o640)
        self.messages = []

    def assert_no_peer(self, fifo):
        with self.assertRaises(OSError) as error:
            fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
            os.close(fd)
        self.assertEqual(error.exception.errno, errno.ENXIO)

    def test_releases_blocking_open_without_transferring_data(self):
        before = self.fifo.stat()
        # Model the blocking open reported by sample(1) on Tahoe. No writer
        # exists until the guard starts, so this also checks the original hang.
        script = """
import os, sys
print('ready', flush=True)
fd = os.open(sys.argv[1], os.O_RDONLY)
os.set_blocking(fd, False)
try:
    assert os.read(fd, 1) == b''
except BlockingIOError:
    pass
os.close(fd)
print('opened without data', flush=True)
"""
        with subprocess.Popen(
            [sys.executable, "-c", script, str(self.fifo)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ) as reader:
            try:
                self.assertEqual(reader.stdout.readline(), "ready\n")
                with self.assertRaises(subprocess.TimeoutExpired):
                    reader.communicate(timeout=0.2)
                with keep_fifos_open(self.source, self.messages.append):
                    output, errors = reader.communicate(timeout=5)
                    self.assertEqual(reader.returncode, 0, errors)
                    self.assertIn("opened without data", output)
            finally:
                if reader.poll() is None:
                    reader.kill()
                    reader.communicate()
        after = self.fifo.stat()
        self.assertTrue(stat.S_ISFIFO(after.st_mode))
        for attribute in ("st_ino", "st_mode", "st_uid", "st_gid", "st_size", "st_mtime_ns"):
            self.assertEqual(getattr(before, attribute), getattr(after, attribute))
        self.assert_no_peer(self.fifo)

    def test_nested_pipes_and_cleanup_after_copy_error(self):
        nested = self.source / "private" / "var" / "spool" / "postfix" / "public"
        nested.mkdir(parents=True)
        second = nested / "qmgr"
        os.mkfifo(second)
        with self.assertRaisesRegex(RuntimeError, "copy failed"):
            with keep_fifos_open(self.source, self.messages.append):
                for fifo in (self.fifo, second):
                    fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
                    os.close(fd)
                raise RuntimeError("copy failed")
        for fifo in (self.fifo, second):
            self.assert_no_peer(fifo)

    def test_setup_failure_closes_previously_opened_pipes(self):
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
            with self.assertRaises(OSError):
                with keep_fifos_open(self.source, self.messages.append):
                    self.fail("Copy must not start when a FIFO cannot be guarded")
        self.assert_no_peer(self.fifo)
        self.assert_no_peer(second)

    def test_does_not_follow_internal_symlinks_or_create_paths(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        outside_fifo = outside / "qmgr"
        os.mkfifo(outside_fifo)
        (self.source / "linked-directory").symlink_to(outside, target_is_directory=True)
        (self.source / "linked-pipe").symlink_to(outside_fifo)
        (self.source / "missing").symlink_to(outside / "absent")
        with keep_fifos_open(self.source, self.messages.append):
            self.assert_no_peer(outside_fifo)
        self.assertEqual(len(self.messages), 1)
        self.assertFalse((outside / "absent").exists())

    def test_rejects_fifo_replaced_by_symlink(self):
        target = self.source / "ordinary.txt"
        target.write_text("untouched")
        self.fifo.unlink()
        self.fifo.symlink_to(target)
        with patch("shared.fifos._find_fifos", return_value=iter([self.fifo])):
            with self.assertRaises(OSError):
                with keep_fifos_open(self.source, self.messages.append):
                    self.fail("Copy must not start after FIFO replacement")
        self.assertEqual(target.read_text(), "untouched")

    @unittest.skipUnless(sys.platform == "darwin", "Requires macOS Ditto")
    def test_ditto_preserves_fsevents_links_and_metadata(self):
        events = self.source / ".fseventsd"
        events.mkdir()
        event = events / "0000000000000001"
        payload = b"synthetic FSEvents fixture\x00\xff"
        event.write_bytes(payload)
        os.chmod(event, 0o640)
        os.utime(event, (1700000000, 1700000000))
        subprocess.run(["xattr", "-w", "com.fuji.test", "metadata", str(event)], check=True)
        os.link(event, events / "hardlink")
        (self.source / "event-link").symlink_to(".fseventsd/0000000000000001")
        (self.source / "empty directory").mkdir()
        unusual = self.source / "name with spaces\tand\na newline"
        unusual.write_text("included")
        destination = Path(self.temp.name) / "copy"
        with keep_fifos_open(self.source, self.messages.append):
            result = subprocess.run(
                ["/usr/bin/ditto", "-X", "-V", str(self.source), str(destination)],
                capture_output=True, text=True, timeout=15,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        copied = destination / ".fseventsd" / event.name
        self.assertEqual(copied.read_bytes(), payload)
        self.assertEqual(
            subprocess.check_output(["xattr", "-p", "com.fuji.test", str(copied)]).strip(),
            b"metadata",
        )
        self.assertEqual(copied.stat().st_mode, event.stat().st_mode)
        self.assertEqual(copied.stat().st_mtime_ns, event.stat().st_mtime_ns)
        self.assertEqual(copied.stat().st_ino, (copied.parent / "hardlink").stat().st_ino)
        self.assertEqual(os.readlink(destination / "event-link"), ".fseventsd/0000000000000001")
        self.assertTrue((destination / "empty directory").is_dir())
        self.assertEqual((destination / unusual.name).read_text(), "included")
        # Pipes are ignored by Ditto, as documented in its manual.
        self.assertFalse((destination / "pickup").exists())


if __name__ == "__main__":
    unittest.main()
