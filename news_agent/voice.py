"""Voice：TTS 语音新闻简报（中文 Xiaoxiao + 美式 Jenny）"""

import asyncio
import logging
import re
from pathlib import Path
from typing import List, Optional

from .models import NewsItem

logger = logging.getLogger(__name__)

try:
    import edge_tts
except ImportError:
    edge_tts = None


class VoiceBriefing:
    """用 edge-tts 生成中英双语语音新闻简报"""

    ZH_VOICE = "zh-CN-XiaoxiaoNeural"    # 自然温柔，像电台主播
    EN_VOICE = "en-US-JennyNeural"        # 标准美式发音，清晰流畅

    def __init__(self, config: dict):
        vcfg = config.get("voice", {})
        self.enabled = vcfg.get("enabled", False) and edge_tts is not None
        self.max_items = vcfg.get("max_items", 5)  # 每段语言最多读 N 条
        out_dir = config.get("render", {}).get("output_dir", "output")
        self.out_dir = Path(out_dir)

        if vcfg.get("enabled") and edge_tts is None:
            logger.warning("edge-tts 未安装，语音简报不可用：pip install edge-tts")
        elif self.enabled:
            logger.info("语音简报已启用（中文→美式英语，最多各 %d 条）", self.max_items)

    def generate(self, items: List[NewsItem], date_str: str) -> Optional[Path]:
        if not self.enabled:
            return None

        zh_items = [i for i in items if i.lang == "zh"][:self.max_items]
        en_items = [i for i in items if i.lang == "en"][:self.max_items]

        if not zh_items and not en_items:
            logger.info("没有新闻可朗读，跳过语音生成")
            return None

        ssml = self._build_ssml(zh_items, en_items, date_str)
        output_path = self.out_dir / f"daily_{date_str.replace('-', '')}.mp3"

        try:
            asyncio.run(self._synthesize(ssml, output_path))
            logger.info("语音简报已生成: %s (%.0fKB)",
                        output_path, output_path.stat().st_size / 1024)
            return output_path
        except Exception as e:
            logger.warning("语音生成失败: %s", e)
            return None

    # ------------------------------------------------------------------
    # 工具方法

    @staticmethod
    def _strip_urls(text: str) -> str:
        """去掉文本中的网址，TTS 不会把它读出来"""
        return re.sub(r'https?://[^\s,。，）)]+', '', text).strip()

    # ------------------------------------------------------------------

    def _build_ssml(self, zh_items: List[NewsItem],
                    en_items: List[NewsItem], date_str: str) -> str:
        """构建 SSML：前半段中文（Xiaoxiao），后半段英文（Jenny），一次合成"""
        zh_part = self._zh_script(zh_items, date_str)
        en_part = self._en_script(en_items)

        return (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis"'
            f' xml:lang="zh-CN">'
            f'<voice name="{self.ZH_VOICE}">{zh_part}</voice>'
            f'<voice name="{self.EN_VOICE}">{en_part}</voice>'
            f'</speak>'
        )

    def _zh_script(self, items: List[NewsItem], date_str: str) -> str:
        parts = []
        # 日期转口语："2026-07-29" → "2026年7月29日"
        spoken_date = f"{date_str.split('-')[0]}年{int(date_str.split('-')[1])}月{int(date_str.split('-')[2])}日"
        parts.append(f"早上好，今天是{spoken_date}，欢迎收听每日新闻简报。")

        if not items:
            parts.append("今天没有符合筛选条件的中文新闻。")
            return "。".join(parts)

        parts.append(f"首先为您带来{len(items)}条中文新闻。")
        for i, item in enumerate(items, 1):
            title = self._strip_urls(item.title)
            summary = self._strip_urls((item.summary or "")[:80].rstrip("。"))
            parts.append(f"第{i}条，来自{item.source}：{title}。{summary}。")

        return "。".join(parts)

    def _en_script(self, items: List[NewsItem]) -> str:
        parts = []

        if not items:
            parts.append("There are no English news stories that match today's filter.")
            return " ".join(parts)

        parts.append("Now for international news.")
        for i, item in enumerate(items, 1):
            summary = (item.summary or "")[:120].rstrip(".")
            title = item.title.strip().rstrip(".")
            title = self._strip_urls(title)
            summary = self._strip_urls(summary)
            parts.append(f"Story {i} from {item.source}: {title}. {summary}.")

        parts.append("That's all for today's briefing. Have a great day!")
        return " ".join(parts)

    async def _synthesize(self, ssml: str, output_path: Path):
        """异步调用 edge-tts，SSML 中已包含语音切换指令"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        communicate = edge_tts.Communicate(ssml)
        await communicate.save(str(output_path))
