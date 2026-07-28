"""M5 Filter：内容筛选 — 按分类关键词过滤新闻条目"""

import logging
from typing import List

from .models import NewsItem

logger = logging.getLogger(__name__)


class ContentFilter:
    """根据配置的分类关键词，筛选保留匹配的新闻"""

    def __init__(self, config: dict):
        fcfg = config.get("filter", {})
        self.enabled = fcfg.get("enabled", False)
        self.match_on = fcfg.get("match_on", "title+text")  # title | title+text
        self.categories = fcfg.get("categories", [])

        # 预编译所有关键词（小写），加速匹配
        self._keywords: List[str] = []
        for cat in self.categories:
            for kw in cat.get("keywords", []):
                for single in kw.split(","):
                    single = single.strip().lower()
                    if single:
                        self._keywords.append(single)

        if self.enabled and self._keywords:
            logger.info("内容筛选已启用（%s），%d 个关键词，覆盖 %d 个分类",
                        self.match_on, len(self._keywords), len(self.categories))
        elif self.enabled and not self._keywords:
            logger.warning("内容筛选已启用但未配置关键词，所有新闻将通过")

    def filter(self, items: List[NewsItem]) -> List[NewsItem]:
        """筛选：保留匹配任一关键词的条目"""
        if not self.enabled or not self._keywords:
            return items

        before = len(items)
        kept = [it for it in items if self._match(it)]
        dropped = before - len(kept)

        if dropped:
            for it in items:
                if it not in kept:
                    logger.debug("筛选丢弃: [%s] %s", it.source, it.title)
            logger.info("内容筛选完成：保留 %d / 丢弃 %d 条",
                        len(kept), dropped)
        else:
            logger.info("内容筛选完成：全部 %d 条通过", len(kept))

        return kept

    def _match(self, item: NewsItem) -> bool:
        """检查单条是否匹配任一关键词"""
        text = item.title.lower()
        if self.match_on == "title+text" and item.text:
            text += " " + item.text.lower()

        return any(kw in text for kw in self._keywords)
