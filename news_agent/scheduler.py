"""M4 Scheduler：APScheduler 常驻调度（--serve 模式）"""
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


def serve(run_once, cron_expr: str) -> None:
    """常驻进程，按 cron 表达式循环执行流水线

    生产环境建议配合 systemd/supervisor 守护：
      [Service]
      ExecStart=/usr/bin/python3 /opt/news_agent/main.py --serve
      Restart=always
    """
    scheduler = BlockingScheduler()
    scheduler.add_job(run_once, CronTrigger.from_crontab(cron_expr),
                      id="daily_news", misfire_grace_time=3600,
                      coalesce=True)  # 错过执行时补跑一次，且不堆积
    logger.info("调度器已启动，cron: %s（Ctrl+C 退出）", cron_expr)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("调度器已停止")
