import codecs
import hashlib
from pathlib import PurePath

MAX_BYTES = 5 * 1024 * 1024
MAX_LINE = 256 * 1024
MAX_LINES = 30000


class UploadError(ValueError):
    pass


class Upload:
    def __init__(self, store, filename):
        if not filename or len(filename) > 180 or '/' in filename or '\\' in filename or '\x00' in filename:
            raise UploadError('Use a simple .log or .txt filename')
        if PurePath(filename).suffix.lower() not in ('.log','.txt'):
            raise UploadError('Only .log and .txt uploads are supported')
        self.store = store
        self.id = store.create(filename)
        self.decoder = codecs.getincrementaldecoder('utf-8-sig')('strict')
        self.hash = hashlib.sha256()
        self.buffer = ''
        self.size = self.number = self.nonblank = 0
        self.batch = []

    def abort(self):
        self.store.delete(self.id)

    def feed(self, block):
        self.size += len(block)
        if self.size > MAX_BYTES:
            raise UploadError('Upload exceeds the 5 MiB limit')
        self.hash.update(block)
        try:
            self.accept(self.decoder.decode(block))
        except UnicodeDecodeError as e:
            raise UploadError('Upload must be valid UTF-8 text') from e

    def accept(self, text):
        if any(ord(c) < 32 and c not in '\r\n\t' for c in text):
            raise UploadError('Binary/control-byte uploads are not supported')
        self.buffer += text
        while '\n' in self.buffer:
            line,self.buffer = self.buffer.split('\n',1)
            self.line(line.removesuffix('\r'))
        if len(self.buffer) > MAX_LINE:
            raise UploadError('A single line exceeds 256 Ki characters')

    def line(self, text):
        if len(text) > MAX_LINE:
            raise UploadError('A single line exceeds 256 Ki characters')
        self.number += 1
        if self.number > MAX_LINES:
            raise UploadError('Upload exceeds 30,000 physical lines')
        self.nonblank += bool(text.strip())
        self.batch.append((self.number,text))
        if len(self.batch) >= 64:
            self.flush()

    def flush(self):
        self.store.append(self.id,self.batch)
        self.batch.clear()

    def finish(self):
        try:
            self.accept(self.decoder.decode(b'', final=True))
        except UnicodeDecodeError as e:
            raise UploadError('Upload ends in incomplete UTF-8') from e
        if self.buffer:
            self.line(self.buffer.removesuffix('\r'))
            self.buffer = ''
        if not self.nonblank:
            raise UploadError('The uploaded log is empty')
        self.flush()
        self.store.update(self.id,bytes=self.size,total_lines=self.number,source_hash=self.hash.hexdigest(),status='ready')
        return self.store.job(self.id)
