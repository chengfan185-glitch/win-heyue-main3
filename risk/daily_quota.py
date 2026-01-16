import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

CN_TZ = timezone(timedelta(hours=8))


class DailyQuotaManager:
    def __init__(self, quota_file: str, daily_limit: int):
        self.quota_file = Path(quota_file)
        self.daily_limit = daily_limit
        self._ensure_file()

    def _today_cn(self) -> str:
        return datetime.now(CN_TZ).strftime("%Y-%m-%d")

    def _ensure_file(self):
        if not self.quota_file.exists():
            self._write_new_day()

    def _read(self) -> dict:
        try:
            return json.loads(self.quota_file.read_text(encoding="utf-8"))
        except Exception:
            return self._write_new_day()

    def _write(self, data: dict):
        self.quota_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def _write_new_day(self) -> dict:
        data = {
            "date": self._today_cn(),
            "remaining": self.daily_limit,
        }
        self._write(data)
        return data

    def refresh_if_new_day(self) -> dict:
        data = self._read()
        today = self._today_cn()

        if data.get("date") != today:
            data = self._write_new_day()

        return data

    def get_remaining(self) -> int:
        data = self.refresh_if_new_day()
        return int(data.get("remaining", 0))

    def consume_one(self) -> int:
        data = self.refresh_if_new_day()

        if data["remaining"] <= 0:
            return 0

        data["remaining"] -= 1
        self._write(data)
        return data["remaining"]
