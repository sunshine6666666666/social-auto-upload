import asyncio
import json
import tempfile
import unittest
from argparse import Namespace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import sau_cli
from uploader.douyin_uploader.main import DouYinVideo
from uploader.douyin_uploader.paid_video import DouyinPaidVideoSettings, parse_peach_douyin_target
from utils.account_identity import AccountIdentity
from utils.browser_selector import BrowserTarget


class PaidVideoParserTests(unittest.TestCase):
    def valid_paid(self, **overrides):
        value = {
            "enabled": True,
            "saleModeText": "单点售卖",
            "priceModeText": "付费视频",
            "priceYuan": 1,
            "productTitle": "SAU付费功能测试",
            "coverModeText": "当前封面",
            "coverAssetRef": None,
            "trialEnabled": True,
            "trialStartSec": 0,
            "trialEndSec": 15,
            "marketingManaged": False,
            "subtitleModeText": "使用成片内已有双语字幕",
            "agreementConfirmed": True,
            "collectionId": None,
        }
        value.update(overrides)
        return value

    def valid_target(self, **overrides):
        return {
            "platform": "douyin",
            "platformAccountId": "stable-douyin-id",
            "settings": {"douyin": {"paidVideo": self.valid_paid(**overrides)}},
        }

    def test_valid_target_normalizes_money_and_title(self):
        account_id, settings = parse_peach_douyin_target(
            self.valid_target(productTitle="  标题  "), video_duration_sec=48.5
        )
        self.assertEqual(account_id, "stable-douyin-id")
        self.assertEqual(settings.price_yuan, Decimal("1.00"))
        self.assertEqual(settings.product_title, "标题")
        self.assertEqual(settings.to_snapshot()["priceYuan"], "1.00")

    def test_accepts_peach_json_number_and_legacy_decimal_string(self):
        for price in (3, 1.25, "1.25"):
            with self.subTest(price=price):
                _, settings = parse_peach_douyin_target(
                    self.valid_target(priceYuan=price), video_duration_sec=48.5
                )
                self.assertEqual(settings.price_yuan, Decimal(str(price)))

    def test_strict_money_and_enum_boundaries(self):
        for overrides in (
            {"priceYuan": "0.99"},
            {"priceYuan": "1000.01"},
            {"priceYuan": "1.001"},
            {"priceYuan": True},
            {"priceModeText": "付费直播"},
            {"subtitleModeText": "使用AI自动生成双语字幕"},
            {"productTitle": "x" * 29},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    parse_peach_douyin_target(self.valid_target(**overrides), video_duration_sec=48.5)

    def test_trial_and_agreement_fail_closed(self):
        for overrides, duration in (
            ({"trialStartSec": 4, "trialEndSec": 13}, 48.5),
            ({"trialStartSec": 0, "trialEndSec": 25}, 48.5),
            ({"agreementConfirmed": False}, 48.5),
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    parse_peach_douyin_target(self.valid_target(**overrides), video_duration_sec=duration)

    def test_target_and_cover_contracts_fail_closed(self):
        with self.assertRaises(ValueError):
            parse_peach_douyin_target({**self.valid_target(), "platform": "youtube"}, video_duration_sec=48.5)
        with self.assertRaises(ValueError):
            parse_peach_douyin_target(
                {key: value for key, value in self.valid_target().items() if key != "platformAccountId"},
                video_duration_sec=48.5,
            )
        with self.assertRaises(ValueError):
            parse_peach_douyin_target(
                self.valid_target(coverModeText="更改封面", coverAssetRef="missing.png"),
                video_duration_sec=48.5,
                base_dir=tempfile.gettempdir(),
            )


class PaidVideoCliTests(PaidVideoParserTests):
    def test_parser_accepts_paid_config_and_no_submit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = Path(temp_dir) / "demo.mp4"
            config = Path(temp_dir) / "target.json"
            video.write_bytes(b"video")
            config.write_text(json.dumps(self.valid_target(), ensure_ascii=False), encoding="utf-8")
            args = sau_cli.build_parser().parse_args(
                [
                    "douyin", "upload-video", "--account", "creator",
                    "--file", str(video), "--title", "paid",
                    "--paid-target-config", str(config), "--no-submit",
                ]
            )
        self.assertFalse(args.submit)
        self.assertEqual(args.paid_target_config, config)

    def test_parser_rejects_schedule_and_no_submit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = Path(temp_dir) / "demo.mp4"
            video.write_bytes(b"video")
            with self.assertRaises(SystemExit):
                sau_cli.build_parser().parse_args(
                    [
                        "douyin", "upload-video", "--account", "creator",
                        "--file", str(video), "--title", "paid",
                        "--schedule", "2099-01-01 00:00", "--no-submit",
                    ]
                )

    def _dispatch_args(self, video, config, **overrides):
        values = dict(
            platform="douyin", action="upload-video", account="creator", file=video,
            title="paid", desc="", tags="", schedule=None, submit=False,
            paid_target_config=config, thumbnail=None, thumbnail_landscape=None,
            thumbnail_portrait=None, product_link="", product_title="",
            declaration="无需添加自主声明", collection=None, target_account=None,
            debug=False, headless=True, browser=None, browsers="", cdp_url=None,
        )
        values.update(overrides)
        return Namespace(**values)

    def test_dispatch_passes_paid_config_and_no_submit_after_target_resolution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "demo.mp4"
            config = root / "target.json"
            video.write_bytes(b"video")
            config.write_text(json.dumps(self.valid_target(), ensure_ascii=False), encoding="utf-8")
            target = BrowserTarget("managed", 9225, "http://127.0.0.1:9225")
            args = self._dispatch_args(video, config)
            with patch("sau_cli.probe_video_duration_seconds", return_value=48.5), patch(
                "sau_cli._resolve_upload_target", new=AsyncMock(return_value=target)
            ), patch("sau_cli.upload_video", new=AsyncMock(return_value={"status": "prepared"})) as upload:
                self.assertEqual(asyncio.run(sau_cli.dispatch(args)), 0)

        request = upload.await_args.args[0]
        self.assertEqual(request.target_account, "stable-douyin-id")
        self.assertEqual(request.paid_video.product_title, "SAU付费功能测试")
        self.assertFalse(request.submit)
        self.assertEqual(request.cdp_url, "http://127.0.0.1:9225")

    def test_dispatch_rejects_target_account_mismatch_before_browser(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "demo.mp4"
            config = root / "target.json"
            video.write_bytes(b"video")
            config.write_text(json.dumps(self.valid_target(), ensure_ascii=False), encoding="utf-8")
            args = self._dispatch_args(video, config, target_account="other-account")
            with patch("sau_cli.probe_video_duration_seconds", return_value=48.5), patch(
                "sau_cli._resolve_upload_target", new=AsyncMock()
            ) as resolve:
                with self.assertRaisesRegex(ValueError, "does not match"):
                    asyncio.run(sau_cli.dispatch(args))
        resolve.assert_not_awaited()


class PaidVideoUiTests(PaidVideoParserTests):
    def _settings(self):
        return DouyinPaidVideoSettings.from_dict(self.valid_paid(), video_duration_sec=48.5)

    def _app(self, **kwargs):
        return DouYinVideo(
            "paid", "demo.mp4", [], 0, "account.json",
            paid_video=self._settings(), **kwargs,
        )

    def test_two_matching_readbacks_verify_paid_settings(self):
        app = self._app()
        app._set_paid_trial = AsyncMock()
        app._paid_agreement = AsyncMock()
        root = SimpleNamespace()
        page = SimpleNamespace(wait_for_timeout=AsyncMock())
        expected = app.paid_video.to_ui_snapshot()
        app._open_paid_video_panel = AsyncMock(return_value=root)
        app._paid_switch = AsyncMock()
        app._paid_radio = AsyncMock()
        app._paid_textbox = AsyncMock()
        app.read_paid_video_settings = AsyncMock(side_effect=[expected, expected])

        result = asyncio.run(app.set_paid_video_settings(page))

        self.assertTrue(result["verified"])
        self.assertEqual(result["observed"], expected)
        self.assertEqual(app.read_paid_video_settings.await_count, 2)

    def test_second_readback_mismatch_blocks(self):
        app = self._app()
        app._set_paid_trial = AsyncMock()
        app._paid_agreement = AsyncMock()
        root = SimpleNamespace()
        page = SimpleNamespace(wait_for_timeout=AsyncMock())
        expected = app.paid_video.to_ui_snapshot()
        app._open_paid_video_panel = AsyncMock(return_value=root)
        app._paid_switch = AsyncMock()
        app._paid_radio = AsyncMock()
        app._paid_textbox = AsyncMock()
        app.read_paid_video_settings = AsyncMock(
            side_effect=[expected, {**expected, "priceYuan": "2.00"}]
        )

        with self.assertRaisesRegex(RuntimeError, "two readbacks"):
            asyncio.run(app.set_paid_video_settings(page))

    def test_disabled_config_does_not_open_paid_ui(self):
        app = self._app()
        app.paid_video = DouyinPaidVideoSettings.from_dict(
            self.valid_paid(enabled=False, agreementConfirmed=False), video_duration_sec=48.5
        )
        app._open_paid_video_panel = AsyncMock()
        app._paid_entry = AsyncMock(
            return_value=(SimpleNamespace(), SimpleNamespace(is_checked=AsyncMock(return_value=False)))
        )
        result = asyncio.run(app.set_paid_video_settings(SimpleNamespace()))
        app._open_paid_video_panel.assert_not_awaited()
        self.assertTrue(result["verified"])
        self.assertEqual(result["observed"], {"enabled": False})

    def test_disabled_config_blocks_when_page_paid_switch_is_on(self):
        app = self._app()
        app.paid_video = DouyinPaidVideoSettings.from_dict(
            self.valid_paid(enabled=False, agreementConfirmed=False), video_duration_sec=48.5
        )
        app._paid_entry = AsyncMock(
            return_value=(SimpleNamespace(), SimpleNamespace(is_checked=AsyncMock(return_value=True)))
        )
        with self.assertRaisesRegex(RuntimeError, "request disables it"):
            asyncio.run(app.set_paid_video_settings(SimpleNamespace()))

    def test_agreement_readback_uses_checkmark_presence(self):
        app = self._app()
        checkmark = SimpleNamespace(count=AsyncMock(side_effect=[0, 1]))
        icon = SimpleNamespace(locator=MagicMock(return_value=checkmark))
        app._paid_agreement_control = AsyncMock(return_value=icon)
        self.assertFalse(asyncio.run(app._read_paid_agreement(SimpleNamespace())))
        self.assertTrue(asyncio.run(app._read_paid_agreement(SimpleNamespace())))

    def test_agreement_clicks_icon_and_verifies_the_new_state(self):
        app = self._app()
        icon = SimpleNamespace(click=AsyncMock())
        app._paid_agreement_control = AsyncMock(return_value=icon)
        app._read_paid_agreement = AsyncMock(side_effect=[False, True])
        asyncio.run(app._paid_agreement(SimpleNamespace(), True))
        icon.click.assert_awaited_once()

    def test_no_submit_returns_prepared_without_finding_publish_button(self):
        app = self._app(submit=False, cdp_url="http://127.0.0.1:9225")
        app.validate_upload_args = AsyncMock()
        app.set_video_file_input = AsyncMock()
        app.set_thumbnail = AsyncMock()
        app.apply_self_declaration = AsyncMock()
        app.fill_title_and_description = AsyncMock()
        app.set_paid_video_settings = AsyncMock(
            return_value={"requested": app.paid_video.to_snapshot(), "observed": {}, "verified": True}
        )

        identity = AccountIdentity("douyin", True, "stable-id", "creator")
        page = MagicMock()
        page.url = "https://creator.douyin.com/creator-micro/content/post/video?enter_from=publish_page"
        page.goto = AsyncMock()
        page.wait_for_url = AsyncMock(side_effect=[None, RuntimeError("version 1"), None])
        page.wait_for_selector = AsyncMock()
        page.locator = MagicMock(side_effect=lambda selector: SimpleNamespace(
            count=AsyncMock(return_value=1 if "long-card" in selector else 0)
        ))
        page.get_by_role = MagicMock(side_effect=AssertionError("publish button must not be queried"))
        session = SimpleNamespace(
            context=SimpleNamespace(),
            new_task_page=AsyncMock(return_value=page),
            close=AsyncMock(),
            focus_fallback_used=False,
        )

        with patch("uploader.douyin_uploader.main.open_browser_session", new=AsyncMock(return_value=session)), patch(
            "uploader.douyin_uploader.main.set_init_script", new=AsyncMock(return_value=session.context)
        ), patch(
            "uploader.douyin_uploader.main.extract_douyin_identity_from_context",
            new=AsyncMock(side_effect=[identity, identity]),
        ), patch(
            "uploader.douyin_uploader.main.save_storage_state_if_owned", new=AsyncMock(return_value=False)
        ):
            result = asyncio.run(app.upload(MagicMock()))

        self.assertEqual(result["status"], "prepared")
        self.assertFalse(result["submitted"])
        self.assertTrue(result["account_match"])
        page.get_by_role.assert_not_called()
        self.assertTrue(app._upload_succeeded)


if __name__ == "__main__":
    unittest.main()
