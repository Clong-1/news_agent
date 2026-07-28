#!/usr/bin/env python3
"""News Agent 入口

用法：
  python main.py --once     # 单次运行完整流水线（cron / GitHub Actions 用）
  python main.py --serve    # 常驻调度（APScheduler，按 config.yaml 的 cron）
"""
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

from news_agent.fetcher import Fetcher
from news_agent.filter import ContentFilter
from news_agent.mailer import Mailer
from news_agent.renderer import Renderer
from news_agent.scheduler import serve
from news_agent.summarizer import Summarizer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("main")


def load_config() -> dict:
    cfg_path = Path(__file__).parent / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_once(config: dict) -> None:
    """完整流水线：抓取 → 正文 → 筛选 → 摘要 → 渲染 → 邮件"""
    start = datetime.now()
    logger.info("=== 新闻助手开始运行 ===")

    fetcher = Fetcher(config)
    items = fetcher.collect()          # 1. 热点列表
    if not items:
        logger.error("未获取到任何热点，终止本次运行")
        return
    items = fetcher.enrich_all(items)  # 2. 正文抽取

    items = ContentFilter(config).filter(items)   # 3. 内容筛选
    if not items:
        logger.error("筛选后无匹配新闻，终止本次运行")
        return

    items = Summarizer(config).summarize_all(items)   # 4. 摘要

    html_path = Renderer(config).render(items)        # 5. 网页

    Mailer(config).send(html_path, items,             # 6. 邮件
                        datetime.now().strftime("%Y-%m-%d"))

    logger.info("=== 运行完成，耗时 %.1f 秒 ===",
                (datetime.now() - start).total_seconds())


def main() -> None:
    # 显式指定 .env 路径（main.py 同级目录），与运行时所在目录无关
    load_dotenv(Path(__file__).parent / ".env")
    parser = argparse.ArgumentParser(description="News Agent 新闻助手")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true", help="单次运行")
    group.add_argument("--serve", action="store_true", help="常驻调度")
    args = parser.parse_args()

    config = load_config()
    if args.once:
        run_once(config)
    else:
        serve(lambda: run_once(config),
              config.get("schedule", {}).get("cron", "30 8 * * *"))


if __name__ == "__main__":
    sys.exit(main())
