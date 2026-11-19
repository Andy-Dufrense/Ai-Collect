"""GitHub 更新重要性规则的离线测试。"""

from __future__ import annotations

import unittest

from github_quality import (
    is_low_value_release,
    is_pirated_software_repository,
    is_significant_commit_message,
    stars_from_summary,
)


class GitHubQualityTests(unittest.TestCase):
    def test_significant_and_routine_commits(self) -> None:
        for message in (
            "feat: add AI stem separation workflow",
            "Implement a local text-to-music inference engine",
            "Add direct Google Lyria music generation support",
        ):
            with self.subTest(message=message):
                self.assertTrue(is_significant_commit_message(message))

        for message in (
            "Add some more log output to audio generation",
            "Increase audio generation retry",
            "fix: improve audio generation response handling",
            "Update documentation",
            "Initial commit - AI Music Generator",
            "https://ai-music-example.streamlit.app/",
        ):
            with self.subTest(message=message):
                self.assertFalse(is_significant_commit_message(message))

    def test_patch_and_prerelease_updates_are_low_value(self) -> None:
        self.assertTrue(
            is_low_value_release(
                "Dependency updates",
                "Bump packages.",
                tag_name="v1.1.1",
            )
        )
        self.assertTrue(
            is_low_value_release(
                "New audio model",
                "Major changes.",
                tag_name="v2.0.0-beta.1",
                prerelease=True,
            )
        )
        self.assertFalse(
            is_low_value_release(
                "MusicGen audio generation engine",
                "Introduces a new model and inference engine.",
                tag_name="v2.0.0",
            )
        )

    def test_pirated_commercial_software_is_rejected(self) -> None:
        self.assertTrue(
            is_pirated_software_repository(
                "FL Studio installer full version download"
            )
        )
        self.assertTrue(
            is_pirated_software_repository(
                "Pro Tools desktop setup with portable mode"
            )
        )
        self.assertFalse(
            is_pirated_software_repository(
                "PULP is a native open-source digital audio workstation"
            )
        )

    def test_stars_are_read_from_summary(self) -> None:
        self.assertEqual(stars_from_summary("主要语言：Python；Stars：63；"), 63)
        self.assertEqual(stars_from_summary("没有星标字段"), 0)


if __name__ == "__main__":
    unittest.main()
