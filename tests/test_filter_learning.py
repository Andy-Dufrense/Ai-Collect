"""人工审核规则生成测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import filter_learning
from scripts.review_filter import parse_answers


class FilterLearningTests(unittest.TestCase):
    def test_answers_are_parsed(self) -> None:
        self.assertEqual(parse_answers("1=y,2=n,3=s"), {1: "y", 2: "n", 3: "s"})

    def test_repeated_rejected_term_becomes_rule(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            decisions = Path(temp_dir) / "decisions.jsonl"
            rules = Path(temp_dir) / "rules.json"
            decisions.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "title": "Gossipartist announces world tour",
                                "decision": "exclude",
                            }
                        ),
                        json.dumps(
                            {
                                "title": "Gossipartist launches new album",
                                "decision": "exclude",
                            }
                        ),
                        json.dumps(
                            {
                                "title": "Suno music software update",
                                "decision": "keep",
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(filter_learning, "DECISIONS_PATH", decisions),
                patch.object(filter_learning, "RULES_PATH", rules),
            ):
                learned = filter_learning.learn_rules_from_decisions()
                self.assertIn("gossipartist", learned["blocked_terms"])
                self.assertTrue(
                    filter_learning.is_learned_excluded(
                        "Gossipartist releases another video"
                    )
                )
                self.assertFalse(
                    filter_learning.is_learned_excluded(
                        "Suno music software update"
                    )
                )


if __name__ == "__main__":
    unittest.main()
