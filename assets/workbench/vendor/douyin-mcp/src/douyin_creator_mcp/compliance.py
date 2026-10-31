"""Platform-terms acknowledgement for browser automation entrypoints."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import PLATFORM_TERMS_ACKNOWLEDGEMENT_REQUIRED, AppError


ACKNOWLEDGEMENT_VERSION = "douyin-automation-risk-v2"
ACKNOWLEDGEMENT_FILENAME = ".platform-risk-acknowledgement.json"
DOUYIN_TERMS_URL = (
    "https://www.douyin.com/agreements/?id=6773906068725565448"
)
DOUYIN_TERMS_UPDATED_DATE = "2026-02-13"
DOUYIN_TERMS_EFFECTIVE_DATE = "2026-02-20"
COMPLIANCE_REVIEWED_DATE = "2026-07-17"
PROJECT_COMPLIANCE_URL = (
    "https://github.com/Kuhakucai/douyin-mcp/blob/main/PLATFORM_COMPLIANCE.md"
)
PLATFORM_COMPLIANCE_NOTICE = (
    "本项目是非官方社区工具，未获抖音授权或背书。抖音用户服务协议第 2.4、"
    "5.1、5.3 和 7.1 条涉及非商业许可、自动化访问、平台信息处理与账号处置风险。"
    "AGPL 允许商业使用本项目代码，但不授予访问抖音、在平台外处理或展示数据、"
    "向第三方提供数据、商业使用平台信息或使用抖音商标的权利。启动浏览器自动化"
    "前，请阅读 PLATFORM_COMPLIANCE.md，并自行确认已获得必要书面授权且符合最新条款。"
)
ACKNOWLEDGEMENT_STATEMENT = (
    "我已阅读抖音用户服务协议第 2.4、5.1、5.3 和 7.1 条及 "
    "PLATFORM_COMPLIANCE.md，理解自动化访问、在平台外处理或展示数据、向 Agent、"
    "模型服务或其他第三方提供数据以及商业使用平台信息可能违反平台条款，并可能"
    "导致功能限制、永久关闭账号或数据删除；我自行负责确认必要书面授权与合规性。"
)


def platform_compliance_status(data_dir: Path) -> dict[str, Any]:
    """Return public acknowledgement state without exposing local paths."""

    payload = _read_acknowledgement(data_dir)
    acknowledged = bool(
        payload and payload.get("version") == ACKNOWLEDGEMENT_VERSION
    )
    return {
        "acknowledged": acknowledged,
        "acknowledgement_version": ACKNOWLEDGEMENT_VERSION,
        "acknowledged_at": payload.get("acknowledged_at") if acknowledged else None,
        "terms_url": DOUYIN_TERMS_URL,
        "terms_updated_date": DOUYIN_TERMS_UPDATED_DATE,
        "terms_effective_date": DOUYIN_TERMS_EFFECTIVE_DATE,
        "compliance_reviewed_date": COMPLIANCE_REVIEWED_DATE,
        "project_compliance_url": PROJECT_COMPLIANCE_URL,
        "notice": PLATFORM_COMPLIANCE_NOTICE,
        "next_action": None
        if acknowledged
        else "运行 douyin-mcp acknowledge-platform-risk --yes 后再启动登录或同步。",
    }


def record_platform_risk_acknowledgement(data_dir: Path) -> dict[str, Any]:
    """Persist an explicit, versioned acknowledgement in the local data directory."""

    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / ACKNOWLEDGEMENT_FILENAME
    temporary = target.with_suffix(".tmp")
    payload = {
        "version": ACKNOWLEDGEMENT_VERSION,
        "acknowledged_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "terms_url": DOUYIN_TERMS_URL,
        "terms_updated_date": DOUYIN_TERMS_UPDATED_DATE,
        "terms_effective_date": DOUYIN_TERMS_EFFECTIVE_DATE,
        "compliance_reviewed_date": COMPLIANCE_REVIEWED_DATE,
        "statement": ACKNOWLEDGEMENT_STATEMENT,
    }
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return platform_compliance_status(data_dir)


def require_platform_risk_acknowledgement(data_dir: Path) -> None:
    """Block browser automation until the current risk notice is acknowledged."""

    status = platform_compliance_status(data_dir)
    if status["acknowledged"]:
        return
    raise AppError(
        PLATFORM_TERMS_ACKNOWLEDGEMENT_REQUIRED,
        "启动浏览器自动化前必须明确确认平台条款风险。",
        retryable=True,
        extra={"platform_compliance": status},
    )


def _read_acknowledgement(data_dir: Path) -> dict[str, Any] | None:
    target = data_dir / ACKNOWLEDGEMENT_FILENAME
    if not target.is_file():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None
