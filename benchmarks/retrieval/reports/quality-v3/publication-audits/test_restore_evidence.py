"""Unit-only restoration fixtures; these bytes are not model or quality evidence."""

from __future__ import annotations

import gzip
import io
import json
import tempfile
import unittest
from pathlib import Path

import restore_evidence as r


class RestorationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.archive = self.root / "archive"
        self.archive.mkdir()
        self.output = self.root / "output"
        self.entries = []

    def tearDown(self):
        self.temp.cleanup()

    def add(self, published, source, raw, encoding="identity", original_gzip=False):
        stored = gzip.compress(raw, mtime=0) if encoding == "gzip" else raw
        original = stored if original_gzip else raw
        row = {
            "published_relative_path": published,
            "source_absolute_path": source,
            "stored_sha256": r.digest(stored),
            "stored_size_bytes": len(stored),
            "raw_sha256": r.digest(raw),
            "raw_size_bytes": len(raw),
            "source_sha256": r.digest(original),
            "source_size_bytes": len(original),
            "encoding": encoding,
            "source_was_gzip": original_gzip,
        }
        p = self.archive / published
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(stored)
        self.entries.append(row)
        return row, original

    def save(self):
        (self.archive / "storage-map-v2.json").write_text(
            json.dumps({"schema_version": 1, "version": 2, "entries": self.entries})
        )

    def test_all_storage_modes_roundtrip_and_identical_skip(self):
        cases = [
            ("plain.txt", "/workspace/work/omnichunk-v3/plain.txt", b"plain\n", "identity", False),
            (
                "plain.json.gz",
                "/workspace/work/omnichunk-v3/plain.json",
                b'{"value":2}\n',
                "gzip",
                False,
            ),
            (
                "original.log.gz",
                "/workspace/work/omnichunk-v3/original.log.gz",
                b"original compressed bytes\n",
                "gzip",
                True,
            ),
            ("external.py", "/external/source.py", b"# external source\n", "identity", False),
        ]
        expected = []
        for p, s, b, e, g in cases:
            row, original = self.add(p, s, b, e, g)
            expected.append((row, original))
        self.save()
        result = r.restore(self.archive, self.output)
        self.assertEqual(result["written"], 4)
        for row, original in expected:
            parts = r.source_destination(
                row["source_absolute_path"],
                r.relative_parts(row["published_relative_path"], "test"),
            )
            self.assertEqual(self.output.joinpath(*parts).read_bytes(), original)
        self.assertEqual(r.restore(self.archive, self.output)["identical_skipped"], 4)

    def test_stored_tamper_rejected_before_output_created(self):
        self.add("artifact.json.gz", "/workspace/work/task/a.json", b"{}", "gzip")
        self.save()
        (self.archive / "artifact.json.gz").write_bytes(b"tampered")
        with self.assertRaisesRegex(r.EvidenceError, "Stored hash/size"):
            r.restore(self.archive, self.output)
        self.assertFalse(self.output.exists())

    def test_original_gzip_filename_and_timestamp_header_is_preserved(self):
        row, _ = self.add(
            "original.gz", "/workspace/work/task/original.gz", b"payload", "gzip", True
        )
        buffer = io.BytesIO()
        with gzip.GzipFile(
            filename="original-header-name", fileobj=buffer, mode="wb", mtime=123
        ) as handle:
            handle.write(b"payload")
        stored = buffer.getvalue()
        row.update(
            stored_sha256=r.digest(stored),
            stored_size_bytes=len(stored),
            source_sha256=r.digest(stored),
            source_size_bytes=len(stored),
        )
        (self.archive / "original.gz").write_bytes(stored)
        self.save()
        r.restore(self.archive, self.output)
        self.assertEqual((self.output / "task/original.gz").read_bytes(), stored)

    def test_raw_and_source_hash_tampering_rejected(self):
        for field in ["raw_sha256", "source_sha256"]:
            with self.subTest(field=field):
                self.entries = []
                row, _ = self.add("a.json.gz", "/workspace/work/task/a.json", b"{}", "gzip")
                row[field] = "0" * 64
                self.save()
                with self.assertRaises(r.EvidenceError):
                    r.restore(self.archive, self.output)
                self.assertFalse(self.output.exists())

    def test_wrong_sizes_rejected(self):
        for field in ["stored_size_bytes", "raw_size_bytes", "source_size_bytes"]:
            with self.subTest(field=field):
                self.entries = []
                row, _ = self.add("a.txt", "/workspace/work/task/a.txt", b"bytes")
                row[field] += 1
                self.save()
                with self.assertRaises(r.EvidenceError):
                    r.restore(self.archive, self.output)

    def test_published_path_traversal_absolute_and_backslash_rejected(self):
        row, _ = self.add("a.txt", "/workspace/work/task/a.txt", b"bytes")
        for value in [
            "../escape",
            "/tmp/escape",
            "nested/../../escape",
            "nested\\escape",
            "nested//escape",
            "C:/escape",
            "file.txt:stream",
        ]:
            with self.subTest(path=value):
                row["published_relative_path"] = value
                self.save()
                with self.assertRaises(r.EvidenceError):
                    r.restore(self.archive, self.output)
                self.assertFalse(self.output.exists())

    def test_source_traversal_rejected(self):
        row, _ = self.add("a.txt", "/workspace/work/../escape", b"bytes")
        self.save()
        with self.assertRaises(r.EvidenceError):
            r.restore(self.archive, self.output)

    def test_existing_different_destination_is_never_overwritten(self):
        self.add("a.txt", "/workspace/work/task/a.txt", b"expected")
        self.save()
        target = self.output / "task/a.txt"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"keep existing")
        with self.assertRaisesRegex(r.EvidenceError, "overwrite differing"):
            r.restore(self.archive, self.output)
        self.assertEqual(target.read_bytes(), b"keep existing")

    def test_archive_symlink_rejected(self):
        self.add("a.txt", "/workspace/work/task/a.txt", b"bytes")
        self.save()
        outside = self.root / "outside"
        outside.write_bytes(b"bytes")
        (self.archive / "a.txt").unlink()
        (self.archive / "a.txt").symlink_to(outside)
        with self.assertRaisesRegex(r.EvidenceError, "Symlink"):
            r.restore(self.archive, self.output)

    def test_destination_symlink_rejected(self):
        self.add("a.txt", "/workspace/work/task/a.txt", b"bytes")
        self.save()
        outside = self.root / "outside"
        outside.mkdir()
        self.output.mkdir()
        (self.output / "task").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(r.EvidenceError, "Symlink"):
            r.restore(self.archive, self.output)
        self.assertFalse((outside / "a.txt").exists())

    def test_destination_collision_and_archive_overlap_rejected(self):
        self.add("a.txt", "/workspace/work/task/a.txt", b"one")
        self.add("b.txt", "/workspace/work/task/a.txt", b"two")
        self.save()
        with self.assertRaisesRegex(r.EvidenceError, "Duplicate restore destination"):
            r.restore(self.archive, self.output)
        with self.assertRaisesRegex(r.EvidenceError, "must not overlap"):
            r.restore(self.archive, self.archive / "out")

    def test_duplicate_manifest_json_key_rejected(self):
        (self.archive / "storage-map-v2.json").write_text('{"version":2,"version":2,"entries":[]}')
        with self.assertRaisesRegex(r.EvidenceError, "Duplicate JSON key"):
            r.restore(self.archive, self.output)


if __name__ == "__main__":
    unittest.main()
