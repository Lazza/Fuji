"""Prevent Ditto's metadata opens from waiting for absent FIFO writers."""

from contextlib import ExitStack, contextmanager
import errno
import os
from pathlib import Path
import stat
from typing import Callable, Iterator


def _find_fifos(source: Path, notify: Callable[[str], None]) -> Iterator[Path]:
    # Match ditto -X: follow the source argument, but neither symlinks inside
    # it nor directories on other devices (including the destination image).
    source = source.resolve(strict=True)
    device = source.stat().st_dev
    pending = [source]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink() or entry.is_file(follow_symlinks=False):
                            continue
                        info = entry.stat(follow_symlinks=False)
                        if info.st_dev != device:
                            continue
                        if stat.S_ISDIR(info.st_mode):
                            pending.append(Path(entry.path))
                        elif stat.S_ISFIFO(info.st_mode):
                            yield Path(entry.path)
                    except OSError as error:
                        notify(f"Cannot inspect {entry.path!r} for named pipes: {error}")
        except OSError as error:
            # Ditto will report any unreadable directories during the copy.
            notify(f"Cannot scan {str(directory)!r} for named pipes: {error}")


@contextmanager
def keep_fifos_open(
    source: Path, notify: Callable[[str], None] = print
) -> Iterator[None]:
    """Hold existing FIFOs open during a copy, without reading or writing data.

    Tahoe's Ditto can block in open() on Postfix FIFOs before ignoring them.
    A nonblocking read/write descriptor supplies the missing peer even in
    Recovery. Keep it open until Ditto exits so the workaround does not race
    with its traversal. Never create a path or follow a FIFO symlink.
    """
    with ExitStack() as descriptors:
        for path in _find_fifos(source, notify):
            # Do not ignore open failures: proceeding with an unguarded FIFO
            # could hang the acquisition. ExitStack also cleans up on failure.
            fd = os.open(path, os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW)
            descriptors.callback(os.close, fd)
            if not stat.S_ISFIFO(os.fstat(fd).st_mode):
                raise OSError(errno.EINVAL, "Named pipe changed during scan", str(path))
            notify(f"Guarding named pipe (no data read or written): {str(path)!r}")
        yield
