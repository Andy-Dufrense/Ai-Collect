"""GitHub Releases 适配器测试。"""

from __future__ import annotations

import unittest

from github_releases import parse_github_releases


class GitHubReleaseTests(unittest.TestCase):
    def test_ai_audio_release_is_parsed(self) -> None:
        payload = [
            {
                "name": "MusicGen audio generation update",
                "tag_name": "v2.0",
                "body": "New AI model and music production features.",
                "html_url": "https://github.com/example/musicgen/releases/v2.0",
                "published_at": "2026-11-17T10:00:00Z",
                "draft": False,
            },
            {
                "name": "Maintenance",
                "tag_name": "v1.1",
                "body": "Dependency updates.",
                "html_url": "https://github.com/example/musicgen/releases/v1.1",
                "published_at": "2026-11-16T10:00:00Z",
                "draft": False,
            },
        ]
        items, total, matched = parse_github_releases(
            payload,
            repository="example/musicgen",
        )
        self.assertEqual(total, 2)
        self.assertEqual(matched, 1)
        self.assertEqual(
            items[0]["title"],
            "GitHub · AI+音乐新发布：MusicGen audio generation update"
            "（example/musicgen）",
        )
        self.assertEqual(items[0]["publish_time"], "2026-11-17T10:00:00+00:00")
        self.assertEqual(items[0]["category"], "AI音频开发")


if __name__ == "__main__":
    unittest.main()
