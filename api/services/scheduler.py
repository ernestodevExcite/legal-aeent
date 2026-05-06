"""
Scheduler de alertas — corre diariamente
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

_scheduler = BackgroundScheduler()


def run_daily_alerts():
    """Job diario de revisión de alertas."""
    from database import get_sync_session
    from routes.alerts import check_expiring_contracts
    try:
        with get_sync_session() as db:
            alerts = check_expiring_contracts(db)
            if alerts:
                print(f"[Scheduler] {len(alerts)} alertas generadas")
    except Exception as e:
        print(f"[Scheduler] Error en job diario: {e}")


def start_scheduler():
    _scheduler.add_job(
        run_daily_alerts,
        CronTrigger(hour=8, minute=0),  # Diariamente a las 8:00 AM
        id="daily_alerts",
        replace_existing=True,
    )
    _scheduler.start()
    print("[Scheduler] Iniciado — alertas diarias a las 08:00")


def stop_scheduler():
    _scheduler.shutdown()
