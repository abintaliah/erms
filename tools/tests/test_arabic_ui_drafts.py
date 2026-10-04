"""Database-free checks for the specified invariant reply prefix."""
import unittest
from tools.generate_arabic_ui_drafts import validate


class ReplyPrefixTests(unittest.TestCase):
    def check_value(self, key, text):
        validate([{"message_key": key, "default_text": "Re:"}],
                 [{"message_key": key, "translated_text": text, "quality_flags": []}])

    def test_specified_reply_prefix_is_invariant(self):
        self.check_value("messaging.reply.subject_prefix", "Re:")

    def test_other_keys_cannot_reuse_exception(self):
        with self.assertRaises(ValueError):
            self.check_value("mobile.other", "Re:")

    def test_other_english_wording_is_still_rejected(self):
        with self.assertRaises(ValueError):
            self.check_value("messaging.reply.subject_prefix", "Reply:")


if __name__ == "__main__":
    unittest.main()
