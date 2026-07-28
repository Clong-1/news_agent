"""M4 Mailer：SMTP 发送 HTML 日报（纯文本 + HTML 双部件，防进垃圾箱）"""
import logging
import os
import smtplib
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
from typing import List

from .models import NewsItem

logger = logging.getLogger(__name__)


class Mailer:
    def __init__(self, config: dict):
        self.enabled = config.get("mail", {}).get("enabled", True)
        self.prefix = config.get("mail", {}).get("subject_prefix", "每日新闻日报")
        self.host = os.environ.get("SMTP_HOST", "")
        self.port = int(os.environ.get("SMTP_PORT", "465"))
        self.user = os.environ.get("SMTP_USER", "")
        self.password = os.environ.get("SMTP_PASS", "")
        self.recipients = [m.strip() for m in
                           os.environ.get("MAIL_TO", "").split(",") if m.strip()]

    def send(self, html_path: Path, items: List[NewsItem], date_str: str) -> bool:
        if not self.enabled:
            logger.info("邮件发送已在配置中关闭，跳过")
            return False
        if not all([self.host, self.user, self.password, self.recipients]):
            logger.error("SMTP 环境变量不完整（SMTP_HOST/USER/PASS/MAIL_TO），跳过发送")
            return False

        html_body = html_path.read_text(encoding="utf-8")
        text_body = self._plain_text(items, date_str)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = Header(f"{self.prefix} {date_str}", "utf-8")
        msg["From"] = formataddr((str(Header("新闻助手", "utf-8")), self.user))
        msg["To"] = ", ".join(self.recipients)
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            with smtplib.SMTP_SSL(self.host, self.port, timeout=30) as smtp:
                smtp.login(self.user, self.password)
                smtp.sendmail(self.user, self.recipients, msg.as_string())
            logger.info("邮件已发送至 %s", self.recipients)
            return True
        except Exception as e:
            logger.error("邮件发送失败: %s", e)
            return False

    @staticmethod
    def _plain_text(items: List[NewsItem], date_str: str) -> str:
        """纯文本降级版：供不支持 HTML 的邮件客户端"""
        lines = [f"每日新闻日报 {date_str}", "=" * 32, ""]
        for i, it in enumerate(items, 1):
            lines.append(f"{i}. [{it.source}] {it.title}")
            if it.summary:
                lines.append(f"   {it.summary}")
            lines.append(f"   原文: {it.url}")
            lines.append("")
        lines.append("—— 由 News Agent 自动生成，摘要仅供快速浏览，详情请阅读原文")
        return "\n".join(lines)
