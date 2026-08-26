from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Mapping


_ALLOWED_SALE_MODE_TEXTS = {"单点售卖", "组合售卖"}
_ALLOWED_PRICE_MODE_TEXTS = {"付费视频", "付费视频（会员免费看）", "会员视频"}
_ALLOWED_COVER_MODE_TEXTS = {"当前封面", "更改封面"}
_ALLOWED_SUBTITLE_MODE_TEXTS = {"使用成片内已有双语字幕"}
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def _require_mapping(value, field_name: str) -> Mapping:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return value


def _require_str(value, field_name: str, *, optional: bool = False) -> str:
    if value is None:
        if optional:
            return ""
        raise ValueError(f"{field_name} must be a non-empty string")
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    text = value.strip()
    if not optional and not text:
        raise ValueError(f"{field_name} must be a non-empty string")
    return text


def _require_bool(value, field_name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _require_one_of(value, field_name: str, allowed: set[str]) -> str:
    text = _require_str(value, field_name)
    if text not in allowed:
        joined = "、".join(sorted(allowed))
        raise ValueError(f"{field_name} must be one of {joined}, got {text}")
    return text


def _parse_price_yuan(raw) -> Decimal:
    if isinstance(raw, bool) or not isinstance(raw, (str, int, float, Decimal)):
        raise ValueError("priceYuan must be a decimal number")
    text = str(raw).strip()
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        raise ValueError("priceYuan must be a non-negative decimal number")
    if "." in text:
        fraction = text.split(".", 1)[1]
        if len(fraction) > 2:
            raise ValueError("priceYuan must not have more than two decimal places")
    price = Decimal(text)
    if price < Decimal("1"):
        raise ValueError("priceYuan must be at least 1")
    if price > Decimal("1000"):
        raise ValueError("priceYuan must be no greater than 1000")
    return price


def _parse_int(raw, field_name: str, *, min_value: int = 0, max_value: int | None = None) -> int:
    if type(raw) is not int:
        raise ValueError(f"{field_name} must be an integer")
    if raw < min_value:
        raise ValueError(f"{field_name} must be >= {min_value}")
    if max_value is not None and raw > max_value:
        raise ValueError(f"{field_name} must be <= {max_value}")
    return raw


def _parse_cover_asset_ref(raw: str | None, *, base_dir: Path) -> Path | None:
    if not raw:
        return None
    if not isinstance(raw, str):
        raise ValueError("coverAssetRef must be a string")
    normalized = raw.strip()
    if not normalized:
        return None
    candidate = Path(normalized)
    if not candidate.is_absolute():
        candidate = (base_dir / candidate).resolve()
    else:
        candidate = candidate.expanduser().resolve()
    if not candidate.exists():
        raise ValueError(f"coverAssetRef path does not exist: {normalized}")
    if not candidate.is_file():
        raise ValueError(f"coverAssetRef must point to a file: {normalized}")
    if candidate.suffix.lower() not in _IMAGE_EXTENSIONS:
        raise ValueError(f"coverAssetRef must be an image path: {normalized}")
    return candidate


@dataclass(frozen=True, slots=True)
class DouyinPaidVideoSettings:
    enabled: bool
    sale_mode_text: str
    price_mode_text: str
    price_yuan: Decimal
    product_title: str
    cover_mode_text: str
    cover_asset_ref: Path | None
    trial_enabled: bool
    trial_start_sec: int
    trial_end_sec: int
    marketing_managed: bool
    subtitle_mode_text: str
    agreement_confirmed: bool
    collection_id: str | None

    @classmethod
    def from_dict(
        cls,
        payload: Mapping,
        *,
        video_duration_sec: float | None = None,
        base_dir: str | Path | None = None,
    ) -> "DouyinPaidVideoSettings":
        raw = _require_mapping(payload, "paidVideo")
        enabled = _require_bool(raw.get("enabled"), "enabled")
        sale_mode_text = _require_one_of(raw.get("saleModeText"), "saleModeText", _ALLOWED_SALE_MODE_TEXTS)
        price_mode_text = _require_one_of(raw.get("priceModeText"), "priceModeText", _ALLOWED_PRICE_MODE_TEXTS)
        price_yuan = _parse_price_yuan(raw.get("priceYuan"))
        product_title = _require_str(raw.get("productTitle"), "productTitle")
        if len(product_title) > 28:
            raise ValueError("productTitle must not exceed 28 characters")
        cover_mode_text = _require_one_of(raw.get("coverModeText"), "coverModeText", _ALLOWED_COVER_MODE_TEXTS)

        directory = Path(base_dir or Path.cwd())
        cover_asset_ref = None
        if cover_mode_text == "更改封面":
            cover_asset_ref = _parse_cover_asset_ref(raw.get("coverAssetRef"), base_dir=directory)
        else:
            if raw.get("coverAssetRef") not in (None, ""):
                raise ValueError("coverAssetRef must be empty or null when coverModeText is 当前封面")

        trial_enabled = _require_bool(raw.get("trialEnabled"), "trialEnabled")
        trial_start_sec = _parse_int(raw.get("trialStartSec"), "trialStartSec", min_value=0)
        trial_end_sec = _parse_int(raw.get("trialEndSec"), "trialEndSec", min_value=0)

        if video_duration_sec is not None and video_duration_sec <= 0:
            raise ValueError("video_duration_sec must be greater than 0")
        if trial_enabled:
            if trial_start_sec >= trial_end_sec:
                raise ValueError("trialStartSec must be less than trialEndSec")
            if (trial_end_sec - trial_start_sec) < 10:
                raise ValueError("trial window must be at least 10 seconds")
            if video_duration_sec is not None and trial_end_sec > (video_duration_sec / 2):
                raise ValueError("trialEndSec exceeds half of video duration")

        marketing_managed = _require_bool(raw.get("marketingManaged"), "marketingManaged")
        subtitle_mode_text = _require_one_of(raw.get("subtitleModeText"), "subtitleModeText", _ALLOWED_SUBTITLE_MODE_TEXTS)

        agreement_confirmed = _require_bool(raw.get("agreementConfirmed"), "agreementConfirmed")
        if enabled and not agreement_confirmed:
            raise ValueError("agreementConfirmed must be true when enabled is true")

        collection_id = raw.get("collectionId")
        if collection_id is not None:
            raise ValueError("collectionId must be null in this version")

        return cls(
            enabled=enabled,
            sale_mode_text=sale_mode_text,
            price_mode_text=price_mode_text,
            price_yuan=price_yuan,
            product_title=product_title,
            cover_mode_text=cover_mode_text,
            cover_asset_ref=cover_asset_ref,
            trial_enabled=trial_enabled,
            trial_start_sec=trial_start_sec,
            trial_end_sec=trial_end_sec,
            marketing_managed=marketing_managed,
            subtitle_mode_text=subtitle_mode_text,
            agreement_confirmed=agreement_confirmed,
            collection_id=collection_id,
        )

    def to_snapshot(self) -> dict:
        return {
            "enabled": self.enabled,
            "saleModeText": self.sale_mode_text,
            "priceModeText": self.price_mode_text,
            "priceYuan": f"{self.price_yuan:.2f}",
            "productTitle": self.product_title,
            "coverModeText": self.cover_mode_text,
            "coverAssetRef": str(self.cover_asset_ref) if self.cover_asset_ref else None,
            "trialEnabled": self.trial_enabled,
            "trialStartSec": self.trial_start_sec,
            "trialEndSec": self.trial_end_sec,
            "marketingManaged": self.marketing_managed,
            "subtitleModeText": self.subtitle_mode_text,
            "agreementConfirmed": self.agreement_confirmed,
            "collectionId": self.collection_id,
        }

    def to_ui_snapshot(self) -> dict:
        snapshot = self.to_snapshot()
        snapshot.pop("subtitleModeText")
        snapshot.pop("collectionId")
        return snapshot



def parse_peach_douyin_target(
    target: Mapping,
    video_duration_sec: float | None,
    base_dir: str | Path | None = None,
) -> tuple[str, DouyinPaidVideoSettings]:
    payload = _require_mapping(target, "target")

    platform = payload.get("platform")
    if platform != "douyin":
        raise ValueError(f"unexpected platform {platform!r}; expected 'douyin'")

    platform_account_id = _require_str(payload.get("platformAccountId"), "platformAccountId")
    settings_root = _require_mapping(payload.get("settings"), "settings")
    douyin_settings = _require_mapping(settings_root.get("douyin"), "settings.douyin")
    paid_payload = _require_mapping(douyin_settings.get("paidVideo"), "settings.douyin.paidVideo")

    return (
        platform_account_id,
        DouyinPaidVideoSettings.from_dict(
            paid_payload,
            video_duration_sec=video_duration_sec,
            base_dir=base_dir,
        ),
    )
