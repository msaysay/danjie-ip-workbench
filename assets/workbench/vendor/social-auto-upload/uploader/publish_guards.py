"""Publish-time checks for Douyin and WeChat Channels.

Video posts must claim originality and mark AI-generated content, and must not
keep a place the form remembered or filled in by itself.
"""
from __future__ import annotations

DOUYIN_AI_LABEL = "内容由AI生成"
TENCENT_AI_LABEL = "含AI生成内容"
ORIGINAL_LABELS = ("声明原创", "原创声明", "视频为原创")
_BLANK_LOCATION = {"不显示位置", "添加位置", "选择位置", "输入地理位置", "位置", "所在位置", "地理位置"}
_CHECKED_CLASS_MARKS = (
    "semi-checkbox-checked",
    "semi-radio-checked",
    "semi-switch-checked",
    "ant-checkbox-checked",
    "weui-desktop-form__checkbox_checked",
)
_TENCENT_LOCATION_SELECTORS = (
    ".post-position-wrap .position-display",
    ".position-display-wrap .position-display",
    "div.position-display",
    "[class*='post-position']",
)


def location_text_is_blank(text: str) -> bool:
    """True when a location control is empty or explicitly says not to show a place."""
    cleaned = " ".join((text or "").replace("\n", " ").split())
    if not cleaned or cleaned in _BLANK_LOCATION:
        return True
    parts = [part for part in cleaned.split(" ") if part not in {"位置", "所在位置", "地理位置"}]
    if not parts:
        return True
    if len(parts) == 1 and parts[0] in _BLANK_LOCATION:
        return True
    return False


def grants_geolocation(location: str | None) -> bool:
    """Typing a place does not need browser geolocation. Never grant it."""
    return False


def _clean(text: str) -> str:
    return " ".join((text or "").replace("\n", " ").split())


async def control_checked(locator) -> bool:
    try:
        if await locator.get_attribute("aria-checked") == "true":
            return True
    except Exception:
        pass
    try:
        class_name = await locator.get_attribute("class") or ""
    except Exception:
        class_name = ""
    if any(mark in class_name for mark in _CHECKED_CLASS_MARKS):
        return True
    try:
        box = locator.locator("input").first
        if await box.count():
            if await box.get_attribute("aria-checked") == "true":
                return True
            try:
                if await box.evaluate("el => !!el.checked"):
                    return True
            except Exception:
                pass
    except Exception:
        pass
    try:
        if await locator.evaluate("el => !!el.checked"):
            return True
    except Exception:
        pass
    return False


async def control_disabled(locator) -> bool:
    try:
        if await locator.get_attribute("aria-disabled") == "true":
            return True
        if await locator.get_attribute("disabled") is not None:
            return True
    except Exception:
        pass
    try:
        box = locator.locator("input").first
        if await box.count():
            try:
                if await box.is_disabled():
                    return True
            except Exception:
                try:
                    if await box.evaluate("el => !!el.disabled"):
                        return True
                except Exception:
                    pass
    except Exception:
        pass
    try:
        if await locator.is_disabled():
            return True
    except Exception:
        pass
    return False


async def _text_visible(page, text: str) -> bool:
    marks = page.get_by_text(text, exact=True)
    try:
        count = await marks.count()
    except Exception:
        return False
    for index in range(count):
        try:
            if await marks.nth(index).is_visible():
                return True
        except Exception:
            continue
    return False


async def find_original_control(page):
    for label in ORIGINAL_LABELS:
        for role in ("checkbox", "switch"):
            candidate = page.get_by_role(role, name=label, exact=True).first
            try:
                if await candidate.count():
                    return candidate
            except Exception:
                continue
    try:
        labels = page.locator("label")
        count = await labels.count()
    except Exception:
        return None
    for index in range(min(count, 40)):
        item = labels.nth(index)
        try:
            text = _clean(await item.inner_text())
        except Exception:
            continue
        if text in ORIGINAL_LABELS:
            return item
    return None


async def confirm_original_dialogs(page) -> None:
    """Agree to the originality terms and close the follow-up dialog, if one opens."""
    for _ in range(4):
        dialog = None
        for selector in (".declare-original-dialog", ".weui-desktop-dialog", ".semi-modal-content", ".ant-modal"):
            candidate = page.locator(selector).first
            try:
                if await candidate.count() and await candidate.is_visible():
                    text = _clean(await candidate.inner_text())
                    if "原创" in text:
                        dialog = candidate
                        break
            except Exception:
                continue
        if dialog is None:
            return
        agree = page.get_by_text("我已阅读并同意", exact=False).first
        try:
            if await agree.count() and await agree.is_visible() and not await control_checked(agree):
                await agree.click()
        except Exception:
            pass
        button = None
        for name in ("声明原创", "确定"):
            try:
                candidate = dialog.get_by_role("button", name=name).first
            except Exception:
                candidate = page.get_by_role("button", name=name).first
            try:
                if await candidate.count() and await candidate.is_visible():
                    button = candidate
                    break
            except Exception:
                continue
        if button is None:
            return
        try:
            await button.click()
            await page.wait_for_timeout(300)
        except Exception:
            return


async def apply_original_claim(page, *, platform_name: str) -> None:
    """Check 原创 and confirm it stayed checked. Raise when it did not."""
    last = f"没有勾上{platform_name}的原创声明"
    for _ in range(3):
        control = await find_original_control(page)
        if control is None:
            last = f"{platform_name}发布页上没有「声明原创」"
            await page.wait_for_timeout(400)
            continue
        if await control_disabled(control):
            raise RuntimeError(f"{platform_name}的「声明原创」现在不可用，已停止发布")
        if not await control_checked(control):
            await control.click()
            await page.wait_for_timeout(300)
        await confirm_original_dialogs(page)
        if await control_checked(control):
            return
        last = f"{platform_name}的「声明原创」点了但没有保持勾选"
        await page.wait_for_timeout(300)
    raise RuntimeError(last + "，已停止发布")


async def apply_tencent_ai_label(page) -> None:
    """Select 含AI生成内容 and confirm the placeholder is gone."""
    last = "没有选中「含AI生成内容」"
    for _ in range(3):
        if await _text_visible(page, TENCENT_AI_LABEL) and not await _text_visible(page, "选择视频标注"):
            return
        opened = False
        for entry_text in ("选择视频标注", "添加标注"):
            entry = page.get_by_text(entry_text, exact=True).first
            try:
                if await entry.count() and await entry.is_visible():
                    await entry.click()
                    opened = True
                    break
            except Exception:
                continue
        if not opened:
            last = "没有找到视频号的「视频标注」"
            await page.wait_for_timeout(400)
            continue
        await page.wait_for_timeout(300)
        option = page.get_by_text(TENCENT_AI_LABEL, exact=True).first
        try:
            await option.wait_for(state="visible", timeout=4000)
            await option.click()
        except Exception:
            last = "视频标注里没有点中「含AI生成内容」"
            await page.wait_for_timeout(300)
            continue
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        await page.wait_for_timeout(300)
        if await _text_visible(page, TENCENT_AI_LABEL) and not await _text_visible(page, "选择视频标注"):
            return
        last = "「含AI生成内容」没有保持选中"
    raise RuntimeError(last + "，已停止发布")


async def declaration_visible(page, declaration: str) -> bool:
    """True when the declaration dialog is closed and the chosen text is still on the form."""
    modals = page.locator(".semi-modal-content")
    try:
        count = await modals.count()
    except Exception:
        count = 0
    for index in range(count):
        item = modals.nth(index)
        try:
            if await item.is_visible() and "请选择声明类型" in _clean(await item.inner_text()):
                return False
        except Exception:
            continue
    return await _text_visible(page, declaration)


async def _tencent_location_display(page):
    for selector in _TENCENT_LOCATION_SELECTORS:
        loc = page.locator(selector).first
        try:
            if not await loc.count() or not await loc.is_visible():
                continue
            # A wrapper around the whole form is not the location field.
            if len(_clean(await loc.inner_text())) > 80:
                continue
            return loc
        except Exception:
            continue
    return None


async def clear_tencent_location(page) -> None:
    """Remove a remembered or suggested WeChat Channels place before submit."""
    display = await _tencent_location_display(page)
    if display is None:
        blank = page.get_by_text("不显示位置", exact=True).first
        try:
            if await blank.count() and await blank.is_visible():
                return
        except Exception:
            pass
        raise RuntimeError("没有找到视频号的位置栏，已停止发布，避免沿用上一次的定位")
    if location_text_is_blank(await display.inner_text()):
        return
    cleared = False
    for selector in (".weui-desktop-icon__close", "[aria-label='清除']", "[aria-label='删除']", "[class*='close']"):
        button = display.locator(selector).first
        try:
            if await button.count() and await button.is_visible():
                await button.click()
                cleared = True
                break
        except Exception:
            continue
    if not cleared:
        await display.click()
        option = page.get_by_text("不显示位置", exact=True).first
        await option.wait_for(state="visible", timeout=4000)
        await option.click()
    await page.wait_for_timeout(300)
    text = _clean(await display.inner_text())
    if not location_text_is_blank(text):
        raise RuntimeError(f"视频号位置没有清掉，仍显示「{text[:40]}」，已停止发布")


async def set_tencent_location(page, location: str) -> None:
    display = await _tencent_location_display(page)
    if display is None:
        raise RuntimeError("没有找到视频号的位置栏，不能填写地点")
    await display.click()
    field = page.locator("input[placeholder*='搜索'], input[placeholder*='位置']").first
    await field.wait_for(state="visible", timeout=4000)
    await field.fill(location)
    await page.wait_for_timeout(400)
    option = page.get_by_text(location, exact=True).first
    await option.click()
    await page.wait_for_timeout(300)
    if location not in _clean(await display.inner_text()):
        raise RuntimeError(f"视频号位置没有写成「{location}」，已停止发布")


async def clear_douyin_location(page, *, required: bool = True) -> None:
    """Clear a Douyin place. GPS is not granted; a leftover POI must still be removed."""
    placeholder = page.locator('div.semi-select span:has-text("输入地理位置")').first
    try:
        count = await placeholder.count()
        visible = bool(count) and await placeholder.is_visible()
    except Exception:
        count, visible = 0, False
    if visible:
        return
    if not count:
        if required:
            raise RuntimeError("没有找到抖音的地理位置，已停止发布，避免浏览器自动带上定位")
        return
    select = placeholder.locator("xpath=ancestor::div[contains(@class,'semi-select')][1]")
    clear = select.locator(".semi-select-clear, .semi-icons-clear, [aria-label='清除']").first
    try:
        if await clear.count():
            await clear.click(force=True)
        else:
            await select.click()
            await page.keyboard.press("Backspace")
            await page.keyboard.press("Escape")
    except Exception as exc:
        raise RuntimeError("抖音地理位置没有清掉，已停止发布，避免带上自动定位") from exc
    await page.wait_for_timeout(300)
    try:
        still_visible = await placeholder.is_visible()
    except Exception:
        still_visible = False
    if not still_visible:
        raise RuntimeError("抖音地理位置没有清掉，已停止发布，避免带上自动定位")
