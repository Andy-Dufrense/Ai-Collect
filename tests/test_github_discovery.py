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
                    "stargazers_count": 16,
                    "language": "Python",
                    "topics": ["ai-music", "audio"],
                },
                {
                    "full_name": "example/website",
                    "description": "Company website",
                    "html_url": "https://github.com/example/website",
                    "created_at": "2026-11-18T02:00:00Z",
                },
                {
                    "full_name": "fake/fl-studio-installer",
                    "description": "FL Studio installer full version download",
                    "html_url": "https://github.com/fake/fl-studio-installer",
                    "created_at": "2026-11-18T01:00:00Z",
                    "stargazers_count": 1200,
                },
                {
                    "full_name": "beginner/ai-music-test",
                    "description": "My first AI music generation practice project",
                    "html_url": "https://github.com/beginner/ai-music-test",
                    "created_at": "2026-11-18T00:00:00Z",
                    "stargazers_count": 4,
                },
                {
                    "full_name": "example/open-daw",
                    "description": (
                        "Open-source digital audio workstation and MIDI editor"
                    ),
                    "html_url": "https://github.com/example/open-daw",
                    "created_at": "2026-11-17T23:00:00Z",
                    "stargazers_count": 500,
                },
                {
                    "full_name": "example/ai-coding-assistant",
                    "description": (
                        "AI coding assistant for software developers"
                    ),
                    "html_url": (
                        "https://github.com/example/ai-coding-assistant"
                    ),
                    "created_at": "2026-11-17T22:00:00Z",
                    "stargazers_count": 500,
                },
            ]
        }

        items, total, matched = parse_repository_search(payload)

        self.assertEqual(total, 6)
        self.assertEqual(matched, 1)
        self.assertEqual(
            items[0]["link"],
            "https://github.com/example/ai-stem-studio",
        )
        self.assertTrue(
            items[0]["title"].startswith(
                "GitHub · AI+音乐新项目：AI music stem separation"
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
                    "repository": {
                        "full_name": "example/ai-music",
                        "stargazers_count": 60,
                    },
                    "commit": {
                        "message": "Add AI music generation workflow\n\nDetails",
                        "committer": {"date": "2026-11-18T04:00:00Z"},
                    },
                },
                {
                    "html_url": (
                        "https://github.com/example/ai-music/commit/def456"
                    ),
                    "repository": {
                        "full_name": "example/ai-music",
                        "stargazers_count": 60,
                    },
                    "commit": {
                        "message": "Update documentation",
                        "committer": {"date": "2026-11-18T03:00:00Z"},
                    },
                },
                {
                    "html_url": (
                        "https://github.com/spam/proxy/commit/spam789"
                    ),
                    "repository": {
                        "full_name": "spam/proxy",
                        "stargazers_count": 500,
                    },
                    "commit": {
                        "message": (
                            "美国海外住宅代理做直播与账号多开"
                            " music update"
                        ),
                        "committer": {"date": "2026-11-18T02:00:00Z"},
                    },
                },
                {
                    "html_url": (
                        "https://github.com/example/agent/commit/ai123"
                    ),
                    "repository": {
                        "full_name": "example/agent",
                        "stargazers_count": 55,
                    },
                    "commit": {
                        "message": "Implement AI agent workflow for audio tools",
                        "committer": {"date": "2026-11-18T01:00:00Z"},
                    },
                },
                {
                    "html_url": (
                        "https://github.com/example/ai-music/commit/log456"
                    ),
                    "repository": {
                        "full_name": "example/ai-music",
                        "stargazers_count": 60,
                    },
                    "commit": {
                        "message": "Add some more log output to audio generation",
                        "committer": {"date": "2026-11-18T00:30:00Z"},
                    },
                },
                {
                    "html_url": (
                        "https://github.com/small/project/commit/small789"
                    ),
                    "repository": {
                        "full_name": "small/project",
                        "stargazers_count": 12,
                    },
                    "commit": {
                        "message": "Add new AI music generation engine",
                        "committer": {"date": "2026-11-18T00:20:00Z"},
                    },
                },
                {
                    "html_url": (
                        "https://github.com/medium/project/commit/medium456"
                    ),
                    "repository": {
                        "full_name": "medium/project",
                        "stargazers_count": 45,
                    },
                    "commit": {
                        "message": "Add music generation engine",
                        "committer": {"date": "2026-11-18T00:10:00Z"},
                    },
                },
            ]
        }

        items, total, matched = parse_commit_search(payload)

        self.assertEqual(total, 7)
        self.assertEqual(matched, 2)
        self.assertEqual(
            items[0]["title"],
            "GitHub · AI+音乐新功能：Add AI music generation workflow"
            "（example/ai-music）",
        )
        self.assertIn("点击标题", items[0]["summary"])
        self.assertTrue(
            any("Implement AI agent workflow" in item["title"] for item in items)
        )


if __name__ == "__main__":
    unittest.main()
