"""WeChat Push：通过 PushPlus 将日报推送到个人微信"""

import logging
import os
from typing import List

from .models import NewsItem

logger = logging.getLogger(__name__)

PUSHPLUS_URL = "https://www.pushplus.plus/send"


class WeChatPusher:
    """调用 PushPlus API 推送新闻摘要到微信"""

    def __init__(self, config: dict):
        wcfg = config.get("wechat", {})
        self.enabled = wcfg.get("enabled", False)
        self.token = os.environ.get("PUSHPLUS_TOKEN", "")
        self.max_items = wcfg.get("max_items", 10)

        if not self.enabled:
            return
        if not self.token:
            logger.warning("微信推送已启用但未配置 PUSHPLUS_TOKEN，跳过")
            self.enabled = False
            return
        logger.info("微信推送已启用（PushPlus），最多 %d 条", self.max_items)

    def send(self, items: List[NewsItem], date_str: str,
             pages_url: str = "") -> bool:
        if not self.enabled:
            return False

        title = self._build_title(items, date_str)
        body = self._build_body(items, date_str, pages_url)

        try:
            import requests
            r = requests.post(
                PUSHPLUS_URL,
                json={"token": self.token,
                      "title": title,
                      "content": body,
                      "template": "html"},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            if data.get("code") == 200:
                logger.info("微信推送成功")
                return True
            else:
                logger.warning("微信推送失败: %s", data.get("msg", "unknown"))
                return False
        except Exception as e:
            logger.warning("微信推送异常: %s", e)
            return False

    # ------------------------------------------------------------------

    def _build_title(self, items: List[NewsItem], date_str: str) -> str:
        zh = sum(1 for i in items if i.lang == "zh")
        en = sum(1 for i in items if i.lang == "en")
        return f"📰 每日新闻日报 {date_str} · 中文{zh}条 英文{en}条"

    def _build_body(self, items: List[NewsItem], date_str: str,
                    pages_url: str = "") -> str:
        disp = items[:self.max_items]
        zh_items = [i for i in disp if i.lang == "zh"]
        en_items = [i for i in disp if i.lang == "en"]

        lines = [f"<h3>📰 每日新闻日报 {date_str}</h3>"]

        if zh_items:
            lines.append("<h4>🇨🇳 中文新闻</h4>")
            for idx, it in enumerate(zh_items, 1):
                summary = (it.summary or "")[:80]
                lines.append(
                    f"<p><b>{idx}. [{it.source}] {it.title}</b><br>"
                    f"{summary}</p>"
                )

        if en_items:
            lines.append("<h4>🌍 International</h4>")
            for idx, it in enumerate(en_items, 1):
                summary = (it.summary or "")[:80]
                lines.append(
                    f"<p><b>{idx}. [{it.source}] {it.title}</b><br>"
                    f"{summary}</p>"
                )

        if pages_url:
            lines.append(
                f'<p style="color:#888;font-size:13px;">'
                f'🔗 <a href="{pages_url}">查看完整日报</a></p>'
            )

        lines.append(
            '<p style="color:#aaa;font-size:12px;">由 News Agent 自动生成</p>'
        )
        return "\n".join(lines)
