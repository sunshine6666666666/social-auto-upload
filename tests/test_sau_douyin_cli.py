import asyncio
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import AsyncMock, patch

import sau_cli
from uploader.douyin_uploader.main import DouYinVideo


class DouyinCliTests(unittest.TestCase):
    def _temp_video(self, temp_dir: str, name: str = "demo.mp4") -> Path:
        video = Path(temp_dir) / name
        video.write_bytes(b"video")
        return video

    def test_build_parser_defaults_declaration_to_no_declaration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = self._temp_video(temp_dir)
            args = sau_cli.build_parser().parse_args(
                [
                    "douyin", "upload-video",
                    "--account", "peach", "--file", str(video),
                    "--title", "hello",
                ]
            )
        self.assertEqual(args.declaration, "无需添加自主声明")
        self.assertIsNone(args.collection)

    def test_build_parser_accepts_explicit_declaration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = self._temp_video(temp_dir)
            args = sau_cli.build_parser().parse_args(
                [
                    "douyin", "upload-video",
                    "--account", "peach", "--file", str(video),
                    "--title", "hello", "--declaration", "内容为个人观点或见解",
                ]
            )
        self.assertEqual(args.declaration, "内容为个人观点或见解")

    def test_build_parser_rejects_unknown_declaration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = self._temp_video(temp_dir)
            with self.assertRaises(SystemExit):
                sau_cli.build_parser().parse_args(
                    [
                        "douyin", "upload-video",
                        "--account", "peach", "--file", str(video),
                        "--title", "hello", "--declaration", "不存在的声明",
                    ]
                )

    def test_build_parser_accepts_collection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = self._temp_video(temp_dir)
            args = sau_cli.build_parser().parse_args(
                [
                    "douyin", "upload-video",
                    "--account", "peach", "--file", str(video),
                    "--title", "hello", "--collection", "英语新闻（训练版）",
                ]
            )
        self.assertEqual(args.collection, "英语新闻（训练版）")

    def test_upload_video_passes_declaration_and_collection_to_uploader(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            account_file = Path(temp_dir) / "account.json"
            account_file.write_text("{}", encoding="utf-8")
            video = self._temp_video(temp_dir)
            request = sau_cli.DouyinVideoUploadRequest(
                account_name="peach",
                video_file=video,
                title="hello",
                description="",
                tags=[],
                publish_date=0,
                declaration="内容由AI生成",
                collection="英语新闻（训练版）",
            )
            with patch("sau_cli.resolve_account_file", return_value=account_file), patch(
                "sau_cli.douyin_setup", new=AsyncMock(return_value=True)
            ), patch(
                "sau_cli.DouYinVideo", autospec=True
            ) as mock_cls:
                mock_cls.return_value.douyin_upload_video = AsyncMock()
                asyncio.run(sau_cli.upload_video(request))

            _, kwargs = mock_cls.call_args
            self.assertEqual(kwargs["declaration"], "内容由AI生成")
            self.assertEqual(kwargs["collection"], "英语新闻（训练版）")

    def test_upload_video_passes_default_declaration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            account_file = Path(temp_dir) / "account.json"
            account_file.write_text("{}", encoding="utf-8")
            video = self._temp_video(temp_dir)
            request = sau_cli.DouyinVideoUploadRequest(
                account_name="peach",
                video_file=video,
                title="hello",
                description="",
                tags=[],
                publish_date=0,
            )
            with patch("sau_cli.resolve_account_file", return_value=account_file), patch(
                "sau_cli.douyin_setup", new=AsyncMock(return_value=True)
            ), patch(
                "sau_cli.DouYinVideo", autospec=True
            ) as mock_cls:
                mock_cls.return_value.douyin_upload_video = AsyncMock()
                asyncio.run(sau_cli.upload_video(request))

            _, kwargs = mock_cls.call_args
            self.assertEqual(kwargs["declaration"], "无需添加自主声明")
            self.assertIsNone(kwargs["collection"])


class DouyinUploaderDefaultTests(unittest.TestCase):
    def test_douyin_video_default_declaration_is_no_declaration(self):
        app = DouYinVideo(
            title="hello",
            file_path="demo.mp4",
            tags=[],
            publish_date=0,
            account_file="account.json",
        )
        self.assertEqual(app.declaration, "无需添加自主声明")
        self.assertIsNone(app.collection)

    def test_douyin_video_explicit_declaration_and_collection(self):
        app = DouYinVideo(
            title="hello",
            file_path="demo.mp4",
            tags=[],
            publish_date=0,
            account_file="account.json",
            declaration="内容为个人观点或见解",
            collection="英语新闻（训练版）",
        )
        self.assertEqual(app.declaration, "内容为个人观点或见解")
        self.assertEqual(app.collection, "英语新闻（训练版）")


if __name__ == "__main__":
    unittest.main()
