import json
import unittest
from unittest.mock import Mock, patch

from utils.direct_cdp import _rpc, _target_for_url, evaluate_cdp, read_page_snapshot


class DirectCdpTests(unittest.TestCase):
    @patch("utils.direct_cdp.subprocess.run")
    def test_rpc_returns_protocol_value_without_printing_it(self, run):
        run.return_value = Mock(returncode=0, stdout=json.dumps({"result": {"value": {"id": "526557505"}}}), stderr="")
        self.assertEqual(_rpc("ws://127.0.0.1/devtools/browser/test", "Runtime.evaluate"), {"value": {"id": "526557505"}})
        run.assert_called_once()

    @patch("utils.direct_cdp.evaluate_cdp")
    def test_page_snapshot_only_consumes_identity_metadata(self, evaluate):
        evaluate.return_value = {
            "url": "https://account.bilibili.com/account/home",
            "title": "个人中心",
            "body": "Stella英语听力磨耳朵",
            "html": "<html></html>",
            "spaceLinks": ["https://space.bilibili.com/526557505"],
        }
        snapshot = read_page_snapshot("http://127.0.0.1:9225", "https://account.bilibili.com/account/home")
        self.assertEqual(snapshot["spaceLinks"], ["https://space.bilibili.com/526557505"])
        evaluate.assert_called_once()
        self.assertTrue(evaluate.call_args.args[2].strip().endswith(")()"))

    @patch("utils.direct_cdp._rpc", return_value={"targetId": "new-target"})
    @patch("utils.direct_cdp._browser_ws", return_value="ws://browser")
    @patch("utils.direct_cdp._targets")
    def test_target_lookup_does_not_hijack_another_same_site_tab(self, targets, _browser_ws, rpc):
        existing = {
            "id": "work-tab",
            "type": "page",
            "url": "https://studio.youtube.com/video/in-progress/edit",
            "webSocketDebuggerUrl": "ws://work-tab",
        }
        created = {
            "id": "new-target",
            "type": "page",
            "url": "https://studio.youtube.com/",
            "webSocketDebuggerUrl": "ws://new-target",
        }
        targets.side_effect = [[existing], [existing, created]]

        result, created_by_call = _target_for_url("http://127.0.0.1:9225", "https://studio.youtube.com/")

        self.assertEqual(result["id"], "new-target")
        self.assertTrue(created_by_call)
        rpc.assert_called_once_with(
            "ws://browser",
            "Target.createTarget",
            {"url": "https://studio.youtube.com/", "background": True},
        )

    @patch("utils.direct_cdp._browser_ws", return_value="ws://browser")
    @patch("utils.direct_cdp._rpc")
    @patch("utils.direct_cdp._target_for_url")
    def test_created_target_is_closed_after_evaluation(self, target_for_url, rpc, _browser_ws):
        target_for_url.return_value = (
            {"id": "new-target", "url": "https://studio.youtube.com/", "webSocketDebuggerUrl": "ws://target"},
            True,
        )
        rpc.return_value = {"result": {"type": "object", "value": {"ok": True}}}

        self.assertEqual(evaluate_cdp("http://127.0.0.1:9225", "https://studio.youtube.com/", "1"), {"ok": True})
        rpc.assert_any_call("ws://browser", "Target.closeTarget", {"targetId": "new-target"})

    @patch("utils.direct_cdp._browser_ws")
    @patch("utils.direct_cdp._rpc")
    @patch("utils.direct_cdp._target_for_url")
    def test_existing_target_is_not_closed(self, target_for_url, rpc, browser_ws):
        target_for_url.return_value = (
            {"id": "existing", "url": "https://studio.youtube.com/", "webSocketDebuggerUrl": "ws://target"},
            False,
        )
        rpc.return_value = {"result": {"type": "object", "value": {"ok": True}}}

        evaluate_cdp("http://127.0.0.1:9225", "https://studio.youtube.com/", "1")
        browser_ws.assert_not_called()
        rpc.assert_called_once()

    @patch("utils.direct_cdp._browser_ws", return_value="ws://browser")
    @patch("utils.direct_cdp._rpc")
    @patch("utils.direct_cdp._target_for_url")
    def test_created_target_is_closed_when_evaluation_fails(self, target_for_url, rpc, _browser_ws):
        target_for_url.return_value = (
            {"id": "new-target", "url": "https://studio.youtube.com/", "webSocketDebuggerUrl": "ws://target"},
            True,
        )
        rpc.side_effect = [RuntimeError("evaluation failed"), {}]

        with self.assertRaisesRegex(RuntimeError, "evaluation failed"):
            evaluate_cdp("http://127.0.0.1:9225", "https://studio.youtube.com/", "1")
        rpc.assert_any_call("ws://browser", "Target.closeTarget", {"targetId": "new-target"})

    @patch("utils.direct_cdp._browser_ws", return_value="ws://browser")
    @patch("utils.direct_cdp._rpc")
    @patch("utils.direct_cdp._targets")
    def test_unavailable_created_target_is_closed(self, targets, rpc, _browser_ws):
        targets.side_effect = [[], *([[]] * 20)]
        rpc.side_effect = [{"targetId": "new-target"}, {}]

        with self.assertRaisesRegex(RuntimeError, "identity tab is unavailable"):
            _target_for_url("http://127.0.0.1:9225", "https://studio.youtube.com/")

        rpc.assert_any_call("ws://browser", "Target.closeTarget", {"targetId": "new-target"})

    @patch("utils.direct_cdp._browser_ws", return_value="ws://browser")
    @patch("utils.direct_cdp._rpc")
    @patch("utils.direct_cdp._target_for_url")
    def test_cleanup_failure_does_not_hide_evaluation_failure(self, target_for_url, rpc, _browser_ws):
        target_for_url.return_value = (
            {"id": "new-target", "url": "https://studio.youtube.com/", "webSocketDebuggerUrl": "ws://target"},
            True,
        )
        rpc.side_effect = [RuntimeError("evaluation failed"), RuntimeError("cleanup failed")]

        with self.assertWarnsRegex(RuntimeWarning, "could not close"):
            with self.assertRaisesRegex(RuntimeError, "evaluation failed"):
                evaluate_cdp("http://127.0.0.1:9225", "https://studio.youtube.com/", "1")
