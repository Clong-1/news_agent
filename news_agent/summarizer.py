"""M2 Summarizer：摘要生成（TextRank 默认 / LLM 可选，自动降级）"""
import logging
import os
from typing import List

from .models import NewsItem

logger = logging.getLogger(__name__)


class Summarizer:
    def __init__(self, config: dict):
        scfg = config.get("summary", {})
        self.method = scfg.get("method", "textrank")
        self.sentences = scfg.get("sentences", 3)
        self.llm_cfg = scfg.get("llm", {})

    def summarize_all(self, items: List[NewsItem]) -> List[NewsItem]:
        for it in items:
            if it.degraded or not it.text:
                it.summary = ""           # 无正文：网页仅展示标题
                continue
            it.summary = self._summarize_one(it)
            it.keywords = it.keywords or self._keywords(it)
        return items

    # ---------- 策略路由 ----------

    def _summarize_one(self, item: NewsItem) -> str:
        if self.method == "llm":
            try:
                return self._llm_summary(item)
            except Exception as e:
                logger.warning("LLM 摘要失败，回退 TextRank: %s", e)
        return self._textrank_summary(item.text, item.lang)

    # ---------- TextRank 抽取式 ----------

    def _textrank_summary(self, text: str, lang: str) -> str:
        try:
            from sumy.nlp.tokenizers import Tokenizer
            from sumy.parsers.plaintext import PlaintextParser
            from sumy.summarizers.text_rank import TextRankSummarizer
            if lang == "zh":
                import jieba
                text = "。".join(
                    " ".join(jieba.cut(s)) for s in text.split("。"))
            parser = PlaintextParser.from_string(
                text, Tokenizer("chinese" if lang == "zh" else "english"))
            summarizer = TextRankSummarizer()
            sents = summarizer(parser.document, self.sentences)
            out = " ".join(str(s).replace(" ", "") if lang == "zh"
                           else str(s) for s in sents)
            return out or text[:300]
        except Exception as e:
            logger.warning("TextRank 摘要失败，截取首段: %s", e)
            return text[:300]

    # ---------- LLM 生成式（OpenAI 兼容） ----------

    def _llm_summary(self, item: NewsItem) -> str:
        import requests
        api_key = os.environ.get("LLM_API_KEY")
        if not api_key:
            raise RuntimeError("缺少 LLM_API_KEY 环境变量")
        limit = "不超过120字" if item.lang == "zh" else "no more than 60 words"
        prompt = (f"请为以下新闻写一段{limit}的摘要，并给出3个关键词"
                  f"（格式：关键词1, 关键词2, 关键词3），用换行分隔。\n\n"
                  f"标题：{item.title}\n正文：{item.text[:4000]}")
        r = requests.post(
            f"{self.llm_cfg.get('base_url', '').rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": self.llm_cfg.get("model", "gpt-4o-mini"),
                  "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": self.llm_cfg.get("max_tokens", 256)},
            timeout=30)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()
        parts = content.split("\n")
        if len(parts) >= 2 and "关键词" in parts[-1] or "," in parts[-1]:
            kws = [k.strip() for k in
                   parts[-1].replace("关键词", "").split(",") if k.strip()]
            item.keywords = [k.lstrip(":：123. ") for k in kws][:3]
            return parts[0].strip()
        return content

    # ---------- 关键词（抽取式路径） ----------

    @staticmethod
    def _keywords(item: NewsItem) -> List[str]:
        try:
            from newspaper import Article
            art = Article(item.url, language=item.lang)
            art.set_html(f"<html><body><p>{item.text}</p></body></html>")
            art.parse()
            art.nlp()
            return list(art.keywords)[:5]
        except Exception:
            return []
