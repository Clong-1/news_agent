"""数据模型定义"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class NewsItem:
    """统一的新闻条目结构，贯穿整条流水线"""
    title: str
    url: str
    source: str                     # 来源名：weibo / BBC World / ...
    lang: str = "zh"                # zh | en
    hot: Optional[int] = None       # 热度值（热榜源有，RSS 无）
    published: Optional[datetime] = None

    # M1 抓取阶段填充
    text: str = ""                  # 正文
    authors: List[str] = field(default_factory=list)
    top_image: Optional[str] = None
    degraded: bool = False          # True = 正文抽取失败，仅标题展示

    # M2 摘要阶段填充
    summary: str = ""
    keywords: List[str] = field(default_factory=list)

    @property
    def hot_fmt(self) -> str:
        """热度人性化显示：1234567 → 123.5万"""
        if not self.hot:
            return ""
        if self.hot >= 10000:
            return f"{self.hot / 10000:.1f}万"
        return str(self.hot)

    @property
    def dedup_key(self) -> str:
        """去重键：规范化 URL + 标题"""
        import hashlib, re
        norm_url = re.sub(r"[?&](utm_\w+|spm|from)=[^&]*", "", self.url)
        return hashlib.sha1(f"{norm_url}|{self.title.strip()}".encode()).hexdigest()
