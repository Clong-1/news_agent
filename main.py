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
from news_agent.voice import VoiceBriefing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("main")


def load_config() -> dict:
    cfg_path = Path(__file__).parent / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_once(config: dict) -> None:
    """完整流水线：抓取 → 正文 → 筛选 → 摘要 → 语音 → 渲染 → 邮件"""
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

    date_str = datetime.now().strftime("%Y-%m-%d")
    audio_path = VoiceBriefing(config).generate(items, date_str)  # 5. 语音简报

    # 语音已生成且配置了 Pages 地址 → 拼公开链接 + 生成二维码（随 output/ 发布）
    voice_url, qr_url = "", ""
    pages_base = config.get("pages", {}).get("base_url", "").rstrip("/")
    if audio_path and pages_base:
        voice_url = f"{pages_base}/{audio_path.name}"
        qr_path = VoiceBriefing.make_qr(
            voice_url,
            audio_path.parent / f"qr_{date_str.replace('-', '')}.png")
        if qr_path:
            qr_url = f"{pages_base}/{qr_path.name}"

    html_path = Renderer(config).render(               # 6. 网页（含语音入口）
        items, voice_url=voice_url, qr_url=qr_url)

    Mailer(config).send(html_path, items, date_str,   # 7. 邮件（含语音附件）
                        audio_path=audio_path)

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
