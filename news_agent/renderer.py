"""M3 Renderer：Jinja2 渲染静态 HTML 日报（内联 CSS，兼容邮件客户端）

支持两种版式（config.yaml -> render.template）：
  newspaper  报纸版式：按热度排序，热度最高的中文新闻为头条
  daily      卡片版式：分区列表
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import List

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .models import NewsItem

logger = logging.getLogger(__name__)


class Renderer:
    def __init__(self, config: dict):
        rcfg = config.get("render", {})
        self.out_dir = Path(rcfg.get("output_dir", "output"))
        self.archive = rcfg.get("archive_by_date", True)
        self.template = rcfg.get("template", "newspaper")  # newspaper | daily
        tpl_dir = Path(__file__).resolve().parent.parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(tpl_dir)),
            autoescape=select_autoescape(["html"]))
        # 模板内可用的 |batch 过滤器：将列表按 n 个一组分批（供多栏布局）
        self.env.filters["batch"] = lambda seq, n: [
            seq[i:i + n] for i in range(0, len(seq), n)]

    def render(self, items: List[NewsItem]) -> Path:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        context = self._build_context(items, now)
        html = self.env.get_template(f"{self.template}.html").render(**context)
        index = self.out_dir / "index.html"
        index.write_text(html, encoding="utf-8")
        if self.archive:
            archive = self.out_dir / f"daily_{now:%Y%m%d}.html"
            archive.write_text(html, encoding="utf-8")
        logger.info("日报已生成（模板 %s）: %s", self.template, index)
        return index

    def _build_context(self, items: List[NewsItem], now: datetime) -> dict:
        base = dict(
            date_str=now.strftime("%Y-%m-%d"),
            time_str=now.strftime("%H:%M"),
            total=len(items),
            degraded=sum(1 for i in items if i.degraded),
            sources=sorted({i.source for i in items}),
            en_items=[i for i in items if i.lang == "en"])
        if self.template == "newspaper":
            # 按热度降序：热度最高的中文新闻成为头条
            zh = sorted((i for i in items if i.lang == "zh"),
                        key=lambda i: i.hot or 0, reverse=True)
            weekdays = ["星期一", "星期二", "星期三", "星期四",
                        "星期五", "星期六", "星期日"]
            base.update(
                headline=zh[0] if zh else None,      # 头条
                sub_heads=zh[1:3],                   # 次头条（第 2、3 名）
                zh_rest=zh[3:],                      # 其余要闻
                weekday_str=weekdays[now.weekday()],
                issue_no=now.strftime("%j").lstrip("0"))  # 年内第几期
        else:
            base.update(zh_items=[i for i in items if i.lang == "zh"])
        return base
