"""M1 Fetcher：热点抓取 + 正文抽取（trafilatura 主 / newspaper4k 备）"""
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import feedparser
import requests

from .models import NewsItem

logger = logging.getLogger(__name__)


class Fetcher:
    def __init__(self, config: dict):
        self.cfg = config
        fcfg = config.get("fetch", {})
        self.timeout = fcfg.get("timeout", 15)
        self.max_workers = fcfg.get("max_workers", 8)
        self.min_text_len = fcfg.get("min_text_len", 200)
        self.session = requests.Session()
        self.session.headers["User-Agent"] = fcfg.get(
            "user_agent", "NewsAgent/1.0")

    # ---------- 热点列表获取 ----------

    def collect(self) -> List[NewsItem]:
        """收集中英文热点条目（仅标题+URL），并去重"""
        items: List[NewsItem] = []
        if self.cfg["sources"].get("hot_api", {}).get("enabled"):
            items += self._from_hot_api()
        if self.cfg["sources"].get("rss", {}).get("enabled"):
            items += self._from_rss()

        seen, unique = set(), []
        for it in items:
            if it.dedup_key not in seen:
                seen.add(it.dedup_key)
                unique.append(it)
        logger.info("收集到 %d 条热点（去重后）", len(unique))
        return unique

    def _from_hot_api(self) -> List[NewsItem]:
        """DailyHotApi 中文热榜：GET {base}/{endpoint} → data[]"""
        hcfg = self.cfg["sources"]["hot_api"]
        base, top_n = hcfg["base_url"].rstrip("/"), hcfg.get("top_n", 5)
        out = []
        for ep in hcfg.get("endpoints", []):
            try:
                r = self.session.get(f"{base}/{ep}", timeout=self.timeout)
                r.raise_for_status()
                for row in (r.json().get("data") or [])[:top_n]:
                    url = row.get("url") or row.get("mobil_url") or ""
                    if row.get("title") and url:
                        out.append(NewsItem(
                            title=row["title"].strip(), url=url,
                            source=ep, lang="zh", hot=row.get("hot")))
            except Exception as e:  # 单源失败不阻断
                logger.warning("热榜源 %s 获取失败: %s", ep, e)
        return out

    def _from_rss(self) -> List[NewsItem]:
        """RSS：feedparser 解析，过滤近 24 小时（支持中英文源，lang 从配置读取）"""
        rcfg = self.cfg["sources"]["rss"]
        top_n = rcfg.get("top_n", 4)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        out = []
        for feed in rcfg.get("feeds", []):
            try:
                d = feedparser.parse(feed["url"])
                count = 0
                for e in d.entries:
                    pub = None
                    if getattr(e, "published_parsed", None):
                        pub = datetime(*e.published_parsed[:6],
                                       tzinfo=timezone.utc)
                    if pub and pub < cutoff:
                        continue  # 只保留近 24h
                    if getattr(e, "title", None) and getattr(e, "link", None):
                        lang = feed.get("lang", "en")  # 每个源可单独指定语言
                        out.append(NewsItem(
                            title=e.title.strip(), url=e.link,
                            source=feed["name"], lang=lang, published=pub))
                        count += 1
                    if count >= top_n:
                        break
            except Exception as e:
                logger.warning("RSS 源 %s 解析失败: %s", feed["name"], e)
        return out

    # ---------- 正文抽取（主备） ----------

    def enrich_all(self, items: List[NewsItem]) -> List[NewsItem]:
        """并发抽取所有条目的正文"""
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(self._enrich_one, it): it for it in items}
            for fu in as_completed(futures):
                try:
                    fu.result()
                except Exception as e:
                    it = futures[fu]
                    it.degraded = True
                    logger.warning("正文抽取异常 [%s]: %s", it.url, e)
        ok = sum(1 for i in items if not i.degraded)
        logger.info("正文抽取完成：成功 %d / 共 %d", ok, len(items))
        return items

    def _enrich_one(self, item: NewsItem) -> None:
        html = self._download(item.url)
        if not html:
            item.degraded = True
            return
        # 主：trafilatura
        text = self._extract_trafilatura(html, item)
        # 备：newspaper4k
        if len(text) < self.min_text_len:
            text = self._extract_newspaper(html, item)
        if len(text) < self.min_text_len:
            item.degraded = True
        item.text = text

    def _download(self, url: str) -> str:
        try:
            r = self.session.get(url, timeout=self.timeout)
            r.raise_for_status()
            return r.text
        except Exception as e:
            logger.debug("下载失败 %s: %s", url, e)
            return ""

    @staticmethod
    def _extract_trafilatura(html: str, item: NewsItem) -> str:
        try:
            import trafilatura
            result = trafilatura.extract(
                html, output_format="json", with_metadata=True,
                include_comments=False, include_tables=False)
            if not result:
                return ""
            import json
            data = json.loads(result)
            if data.get("title"):
                item.title = item.title or data["title"]
            if data.get("author"):
                item.authors = [a.strip() for a in
                                re.split(r"[,;]", data["author"])]
            if data.get("image"):
                item.top_image = data["image"]
            return data.get("text") or ""
        except Exception:
            return ""

    @staticmethod
    def _extract_newspaper(html: str, item: NewsItem) -> str:
        try:
            from newspaper import Article
            art = Article(item.url, language=item.lang)
            art.set_html(html)          # 复用已下载 HTML，避免二次请求
            art.parse()
            item.authors = item.authors or list(art.authors)
            item.top_image = item.top_image or art.top_image
            return art.text or ""
        except Exception:
            return ""
