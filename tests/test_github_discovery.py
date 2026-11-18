"""GitHub 新项目与 commit 自动发现的离线测试。"""

from __future__ import annotations

import unittest

from github_discovery import (
    parse_commit_search,
    parse_repository_search,
)


class GitHubDiscoveryTests(unittest.TestCase):
    def test_new_ai_music_repository_has_summary_and_link(self) -> None:
        payload = {
            "items": [
                {
                    "full_name": "example/ai-stem-studio",
                    "description": "AI music stem separation for DAWs",
                    "html_url": "https://github.com/example/ai-stem-studio",
                    "created_at": "2026-11-18T03:00:00Z",
                    "stargazers_count": 12,
                    "language": "Python",
                    "topics": ["ai-music", "audio"],
                },
                {
                    "full_name": "example/website",
                    "description": "Company website",
                    "html_url": "https://github.com/example/website",
                    "created_at": "2026-11-18T02:00:00Z",
                },
            ]
        }

        items, total, matched = parse_repository_search(payload)

        self.assertEqual(total, 2)
        self.assertEqual(matched, 1)
        self.assertEqual(
            items[0]["link"],
            "https://github.com/example/ai-stem-studio",
        )
        self.assertTrue(
            items[0]["title"].startswith(
                "GitHub - 新发布：AI music stem separation"
            )
        )
        self.assertIn("Python", items[0]["summary"])
        self.assertEqual(items[0]["publish_time"], "2026-11-18T03:00:00+00:00")

    def test_relevant_commit_is_parsed_and_noise_is_skipped(self) -> None:
        payload = {
            "items": [
                {
                    "html_url": (
                        "https://github.com/example/ai-music/commit/abc123"
                    ),
                    "repository": {"full_name": "example/ai-music"},
                    "commit": {
                        "message": "Add AI music generation workflow\n\nDetails",
                        "committer": {"date": "2026-11-18T04:00:00Z"},
                    },
                },
                {
                    "html_url": (
                        "https://github.com/example/ai-music/commit/def456"
                    ),
                    "repository": {"full_name": "example/ai-music"},
                    "commit": {
                        "message": "Update documentation",
                        "committer": {"date": "2026-11-18T03:00:00Z"},
                    },
                },
            ]
        }

        items, total, matched = parse_commit_search(payload)

        self.assertEqual(total, 2)
        self.assertEqual(matched, 1)
        self.assertEqual(
            items[0]["title"],
            "GitHub - 新更新：Add AI music generation workflow"
            "（example/ai-music）",
        )
        self.assertIn("点击标题", items[0]["summary"])


if __name__ == "__main__":
    unittest.main()
