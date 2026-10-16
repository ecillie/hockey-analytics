"""Immutable local artifact storage; cloud implementations share this interface."""
from hashlib import sha256
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Protocol


class ArtifactStore(Protocol):
    def put(self, payload: bytes) -> str: ...
    def read(self, digest: str) -> bytes: ...


class LocalArtifacts:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def _path(self, digest):
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("Artifact key must be a SHA-256 digest")
        return self.root / (digest + ".json")

    def put(self, payload):
        digest = sha256(payload).hexdigest()
        destination = self._path(digest)
        self.root.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=self.root, delete=False) as temporary:
            pending = Path(temporary.name)
            try:
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
                try:
                    os.link(pending, destination)
                except FileExistsError:
                    if self.read(digest) != payload:
                        raise ValueError("Artifact content conflict")
                directory = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                pending.unlink(missing_ok=True)
        return digest

    def read(self, digest):
        payload = self._path(digest).read_bytes()
        if sha256(payload).hexdigest() != digest:
            raise ValueError("Artifact digest differs")
        return payload
