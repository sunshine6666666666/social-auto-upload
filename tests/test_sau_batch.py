import asyncio
import json
import os
import tempfile
import threading
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import AsyncMock, patch

import sau_cli
from utils.browser_runtime import begin_task, browser_task_lock, finish_task
from utils.browser_selector import BrowserTarget


class BrowserTaskStateTests(unittest.TestCase):
    def test_lock_rejects_live_owner_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as state_dir, patch.dict(os.environ, {"SAU_TASK_STATE_DIR": state_dir}):
            with browser_task_lock(9225):
                with self.assertRaisesRegex(RuntimeError, "already in use"):
                    with browser_task_lock(9225):
                        pass
            self.assertFalse((Path(state_dir) / "browser-9225.lock").exists())

    def test_dead_lock_is_recovered_once(self):
        with tempfile.TemporaryDirectory() as state_dir, patch.dict(os.environ, {"SAU_TASK_STATE_DIR": state_dir}):
            path = Path(state_dir) / "browser-9225.lock"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("99999999", encoding="ascii")
            with browser_task_lock(9225):
                self.assertTrue(path.exists())
            self.assertFalse(path.exists())

    def test_receipt_is_idempotent_and_rejects_hash_conflict(self):
        with tempfile.TemporaryDirectory() as state_dir, patch.dict(os.environ, {"SAU_TASK_STATE_DIR": state_dir}):
            self.assertEqual(begin_task("task-1", ["youtube", "identity"])["state"], "started")
            finish_task("task-1", {"status": "success", "stable_id": "UC1"})
            duplicate = begin_task("task-1", ["youtube", "identity"])
            self.assertEqual(duplicate["state"], "skipped_duplicate")
            with self.assertRaisesRegex(RuntimeError, "different arguments"):
                begin_task("task-1", ["youtube", "check"])

    def test_started_receipt_never_reexecutes(self):
        with tempfile.TemporaryDirectory() as state_dir, patch.dict(os.environ, {"SAU_TASK_STATE_DIR": state_dir}):
            begin_task("task-2", ["youtube", "identity"])
            self.assertEqual(begin_task("task-2", ["youtube", "identity"])["state"], "uncertain")

    def test_concurrent_receipt_claim_has_only_one_started_owner(self):
        with tempfile.TemporaryDirectory() as state_dir, patch.dict(os.environ, {"SAU_TASK_STATE_DIR": state_dir}):
            barrier = threading.Barrier(2)
            states = []

            def claim():
                barrier.wait()
                states.append(begin_task("task-race", ["youtube", "identity"])["state"])

            threads = [threading.Thread(target=claim) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertCountEqual(states, ["started", "uncertain"])

    def test_unknown_receipt_state_fails_closed(self):
        with tempfile.TemporaryDirectory() as state_dir, patch.dict(os.environ, {"SAU_TASK_STATE_DIR": state_dir}):
            begin_task("task-invalid-state", ["youtube", "identity"])
            receipt_path = Path(state_dir) / "task-invalid-state.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["state"] = "mystery"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "invalid state"):
                begin_task("task-invalid-state", ["youtube", "identity"])

    def test_invalid_task_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as state_dir, patch.dict(os.environ, {"SAU_TASK_STATE_DIR": state_dir}):
            with self.assertRaises(ValueError):
                begin_task("../escape", ["youtube", "identity"])


class BatchDispatchTests(unittest.TestCase):
    def _manifest(self, directory: str) -> Path:
        path = Path(directory) / "batch.json"
        path.write_text(
            json.dumps(
                {
                    "tasks": [
                        {"id": "first", "argv": ["youtube", "identity", "--account", "one"]},
                        {"id": "second", "argv": ["youtube", "identity", "--account", "two"]},
                    ]
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_batch_continues_after_failure_and_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"SAU_TASK_STATE_DIR": str(Path(directory) / "state")}
        ), patch("sau_cli.dispatch", new=AsyncMock(side_effect=[1, 0])) as dispatch, patch("builtins.print"):
            result = asyncio.run(sau_cli.dispatch_batch(self._manifest(directory)))
        self.assertEqual(result, 1)
        self.assertEqual(dispatch.await_count, 2)

    def test_complete_task_replay_does_not_call_child(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"SAU_TASK_STATE_DIR": str(Path(directory) / "state")}
        ), patch("sau_cli.dispatch", new=AsyncMock(return_value=0)) as dispatch, patch("builtins.print"):
            manifest = self._manifest(directory)
            self.assertEqual(asyncio.run(sau_cli.dispatch_batch(manifest)), 0)
            self.assertEqual(asyncio.run(sau_cli.dispatch_batch(manifest)), 0)
        self.assertEqual(dispatch.await_count, 2)

    def test_nested_batch_is_rejected_before_child_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested.json"
            path.write_text(json.dumps({"tasks": [{"id": "nested", "argv": ["batch", "--file", str(path)]}]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "nested"):
                sau_cli._validate_batch_manifest(path)

    def test_named_browser_is_resolved_and_locked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "batch.json"
            path.write_text(
                json.dumps(
                    {
                        "tasks": [
                            {
                                "id": "named-browser",
                                "argv": [
                                    "youtube",
                                    "identity",
                                    "--account",
                                    "one",
                                    "--browser",
                                    "managed",
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            target = BrowserTarget("managed", 9225, "http://127.0.0.1:9225")
            with patch.dict(
                os.environ, {"SAU_TASK_STATE_DIR": str(Path(directory) / "state")}
            ), patch("sau_cli.resolve_browser_target", return_value=target), patch(
                "sau_cli.dispatch", new=AsyncMock(return_value=0)
            ), patch("sau_cli.browser_task_lock", wraps=browser_task_lock) as lock, patch(
                "builtins.print"
            ):
                self.assertEqual(asyncio.run(sau_cli.dispatch_batch(path)), 0)
        lock.assert_called_once_with(9225)


class SingleCommandLockTests(unittest.TestCase):
    def test_main_locks_resolved_cdp_port(self):
        target = BrowserTarget("managed", 9225, "http://127.0.0.1:9225")
        with patch("sau_cli.resolve_browser_target", return_value=target), patch(
            "sau_cli.dispatch", new=AsyncMock(return_value=0)
        ), patch("sau_cli.browser_task_lock", wraps=browser_task_lock) as lock, tempfile.TemporaryDirectory() as state_dir, patch.dict(
            os.environ, {"SAU_TASK_STATE_DIR": state_dir}
        ):
            self.assertEqual(
                sau_cli.main(
                    ["youtube", "identity", "--account", "one", "--browser", "managed"]
                ),
                0,
            )
        lock.assert_called_once_with(9225)

    def test_success_receipt_keeps_structured_publish_result(self):
        async def fake_dispatch(args):
            args._last_result = {
                "status": "success",
                "platform": "youtube",
                "videoId": "QMiJvZPJJv0",
                "stable_id": "UC1",
            }
            return 0

        with tempfile.TemporaryDirectory() as state_dir, patch.dict(
            os.environ, {"SAU_TASK_STATE_DIR": state_dir}
        ), patch("sau_cli.dispatch", side_effect=fake_dispatch):
            result = sau_cli.main(
                [
                    "youtube", "upload-video", "--account", "one",
                    "--file", __file__, "--title", "receipt",
                    "--task-id", "structured-result",
                ]
            )
            receipt = json.loads((Path(state_dir) / "structured-result.json").read_text(encoding="utf-8"))

        self.assertEqual(result, 0)
        self.assertEqual(receipt["result"]["videoId"], "QMiJvZPJJv0")
        self.assertEqual(receipt["result"]["stable_id"], "UC1")


if __name__ == "__main__":
    unittest.main()
