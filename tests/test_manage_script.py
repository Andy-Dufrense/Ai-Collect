"""本地启动策略的静态回归测试。"""

from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent


class ManageScriptTests(unittest.TestCase):
    def test_local_start_does_not_launch_auto_fetcher(self) -> None:
        script = (PROJECT_DIR / "manage.sh").read_text(encoding="utf-8")

        self.assertNotIn("start_worker", script)
        self.assertNotIn(
            'nohup "${PYTHON_BIN}" "${PROJECT_DIR}/auto_fetcher.py"',
            script,
        )
        self.assertIn("./manage.sh fetch", script)

    def test_deployment_does_not_install_worker_service(self) -> None:
        install_script = (
            PROJECT_DIR / "deploy" / "install.sh"
        ).read_text(encoding="utf-8")

        self.assertNotIn(
            "systemctl enable --now ai-music-worker.service",
            install_script,
        )
        self.assertFalse(
            (PROJECT_DIR / "deploy" / "ai-music-worker.service").exists()
        )


if __name__ == "__main__":
    unittest.main()
