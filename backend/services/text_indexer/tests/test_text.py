from __future__ import annotations

import unittest
import os
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from backend.services.text_indexer.config import Settings
from backend.services.text_indexer.text import chunks, classify, normalize
from backend.services.text_indexer.tika import ExtractionError, extract_pdf, pdf_page_count
from backend.services.text_indexer.worker import Worker


class TextPolicyTests(unittest.TestCase):
    def test_normalization_removes_controls_and_bounds_chunks(self):
        value = normalize("alpha\x00  beta\r\n\r\n\r\ngamma")
        self.assertEqual(value, "alpha beta\n\ngamma")
        result = chunks("word " * 12_000)
        self.assertTrue(result)
        self.assertTrue(all(len(chunk.text) <= 20_000 for chunk in result))

    def test_language_policy(self):
        self.assertEqual(classify("This is short.")[0], "short")
        self.assertEqual(classify("SELECT value FROM table WHERE id=1")[0], "code_like")
        self.assertEqual(classify("The approved records policy provides reliable evidence. " * 8), ("english", "en"))
        self.assertEqual(classify("توفر سياسة السجلات المعتمدة أدلة موثوقة للمؤسسة. " * 8), ("arabic", "ar"))

    def test_pdf_page_limit_fails_before_extraction(self):
        completed=__import__('subprocess').CompletedProcess(["pdfinfo"],0,"Pages: 1001\n","")
        with patch("backend.services.text_indexer.tika.subprocess.run",return_value=completed):
            self.assertEqual(pdf_page_count(Path("document.pdf")),1001)
        with patch("backend.services.text_indexer.tika.pdf_page_count",return_value=1001), \
             patch("backend.services.text_indexer.tika.extract") as tika_extract:
            with self.assertRaisesRegex(ExtractionError,"page limit"):
                extract_pdf(Path("/tika"),Path("/tmp/document.pdf"),120,1000,1024)
            tika_extract.assert_not_called()

    def test_startup_recovery_removes_only_old_owned_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); stale=root/"wathiq-index-stale"; recent=root/"wathiq-index-recent"; unrelated=root/"keep"
            stale.mkdir(); recent.mkdir(); unrelated.mkdir()
            old=time.time()-7200; os.utime(stale,(old,old))
            settings=Settings("http://127.0.0.1:8000","wti_x","test",Path("/tika"),4,5,60,120,
                              100,1000,100,200,10,1000,root,1,100)
            worker=object.__new__(Worker); worker.settings=settings
            self.assertEqual(worker.recover_temporary_files(),1)
            self.assertFalse(stale.exists()); self.assertTrue(recent.exists()); self.assertTrue(unrelated.exists())

    def test_startup_recovery_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for number in range(3):
                entry=root/f"wathiq-index-{number}"; entry.mkdir()
                old=time.time()-7200-number; os.utime(entry,(old,old))
            settings=Settings("http://127.0.0.1:8000","wti_x","test",Path("/tika"),4,5,60,120,
                              100,1000,100,200,10,1000,root,1,2)
            worker=object.__new__(Worker); worker.settings=settings
            self.assertEqual(worker.recover_temporary_files(),2)
            self.assertEqual(len(list(root.iterdir())),1)


if __name__ == "__main__":
    unittest.main()
