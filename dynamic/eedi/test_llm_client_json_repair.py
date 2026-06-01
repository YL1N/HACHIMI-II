import unittest

from dynamic.eedi.src.llm_client import _extract_first_json_object


class LlmClientJsonRepairTest(unittest.TestCase):
    def test_extracts_json_with_latex_backslash_escapes(self):
        parsed = _extract_first_json_object(
            '{"text": "use \\(2\\\\pi r\\)", "label": "ok"}'
        )

        self.assertEqual(parsed["text"], "use \\(2\\pi r\\)")
        self.assertEqual(parsed["label"], "ok")


if __name__ == "__main__":
    unittest.main()
