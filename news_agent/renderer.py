"""M3 Renderer：Jinja2 渲染静态 HTML 日报（内联 CSS，兼容邮件客户端）"""
import logging
from datetime import datetime
from pathlib import Path
from typing import List

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .models import NewsItem

logger = logging.getLogger(__name__)


class Renderer:
    def __init__(self, config: dict):
        self.out_dir = Path(config.get("render", {})
                            .get("output_dir", "output"))
        self.archive = config.get("render", {}).get("archive_by_date", True)
        tpl_dir = Path(__file__).resolve().parent.parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(tpl_dir)),
            autoescape=select_autoescape(["html"]))

    def render(self, items: List[NewsItem]) -> Path:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        zh = [i for i in items if i.lang == "zh"]
        en = [i for i in items if i.lang == "en"]
        html = self.env.get_template("daily.html").render(
            date_str=now.strftime("%Y-%m-%d"),
            time_str=now.strftime("%H:%M"),
            zh_items=zh, en_items=en,
            total=len(items),
            degraded=sum(1 for i in items if i.degraded),
            sources=sorted({i.source for i in items}))
        index = self.out_dir / "index.html"
        index.write_text(html, encoding="utf-8")
        if self.archive:
            archive = self.out_dir / f"daily_{now:%Y%m%d}.html"
            archive.write_text(html, encoding="utf-8")
        logger.info("日报已生成: %s", index)
        return index
