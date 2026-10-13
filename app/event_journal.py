"""Bounded, ordered panel logging without storage I/O on the Tk thread."""
from __future__ import print_function
import os
import threading
try:
    import Queue as queue
except ImportError:
    import queue


class EventJournal(object):
    def __init__(self, path, output, capacity=128):
        self.path, self.output = path, output
        self.pending = queue.Queue(maxsize=capacity)
        self.completed = queue.Queue(maxsize=capacity)
        self.error, self.output_error = None, None
        self.done = threading.Event()
        self.closing = False
        self.thread = threading.Thread(target=self._run, name='scr-panel-journal')
        self.thread.daemon = True
        self.thread.start()

    def append(self, line, sequence, durable=False):
        if self.error or self.closing:
            raise IOError(self.error or 'Panel journal is closing')
        try:
            self.pending.put_nowait((line, sequence, durable))
        except queue.Full:
            self.error = 'Panel journal queue is full; event not saved'
            raise IOError(self.error)

    def poll(self):
        result = []
        while True:
            try:
                result.append(self.completed.get_nowait())
            except queue.Empty:
                return result

    def close(self):
        self.closing = True

    def _run(self):
        stream = None
        try:
            if self.path:
                stream = os.fdopen(os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w')
            while not self.closing or not self.pending.empty():
                try:
                    batch = [self.pending.get(timeout=0.05)]
                except queue.Empty:
                    continue
                for unused in range(31):
                    try:
                        batch.append(self.pending.get_nowait())
                    except queue.Empty:
                        break
                lines = ''.join(item[0] for item in batch)
                if stream:
                    stream.write(lines)
                    stream.flush()
                    if any(item[2] for item in batch):
                        os.fsync(stream.fileno())
                    for line, sequence, durable in batch:
                        if durable:
                            self.completed.put_nowait(sequence)
                # Console output is a secondary mirror. Its failure cannot undo
                # a successfully persisted annotation.
                if not self.output_error:
                    try:
                        self.output.write(lines)
                        self.output.flush()
                    except (IOError, OSError) as error:
                        self.output_error = str(error)
                        if not stream:
                            self.error = self.output_error
                if not stream and not self.output_error:
                    for line, sequence, durable in batch:
                        if durable:
                            self.completed.put_nowait(sequence)
            if stream:
                stream.flush()
                os.fsync(stream.fileno())
        except (IOError, OSError, queue.Full) as error:
            self.error = str(error) or 'Panel journal write failed'
        finally:
            if stream:
                try:
                    stream.close()
                except (IOError, OSError) as error:
                    self.error = self.error or str(error)
            self.done.set()
