import unittest

from uploader.alipay_uploader.main import format_title_with_tags


class AlipayUploaderTests(unittest.TestCase):
    def test_title_tags_are_added_only_at_tag_boundaries(self):
        self.assertEqual(
            format_title_with_tags("1234567890", ["abc", "too-long"], max_length=15),
            "1234567890 #abc",
        )

    def test_long_title_is_truncated(self):
        self.assertEqual(format_title_with_tags("123456", [], max_length=4), "1234")


if __name__ == "__main__":
    unittest.main()
