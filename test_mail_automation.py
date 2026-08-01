#!/usr/bin/env python3
"""Send one harmless message through the same path used by scheduled jobs."""
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import mailer

LOCK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", ".mail_smoke_lock")
COOLDOWN_SECONDS = 600


def acquire_lock():
    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    try:
        age = time.time() - os.path.getmtime(LOCK)
        if age < COOLDOWN_SECONDS:
            return False
        os.unlink(LOCK)
    except FileNotFoundError:
        pass
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w") as f:
        f.write(str(int(time.time())))
    return True


def main():
    if not acquire_lock():
        print("SKIP: mail smoke already ran within 10 minutes")
        return 0
    recipient = mailer.load_env().get("MAIL_TO")
    if not recipient:
        os.unlink(LOCK)
        print("ERROR: MAIL_TO not set", file=sys.stderr)
        return 1
    stamp = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")
    try:
        mailer.send_mail(
            recipient,
            "[자동 경로 테스트] BoomyBoom 예약 메일 확인",
            "BoomyBoom 예약 작업과 같은 자동 경로로 보낸 테스트 메일입니다.\n\n"
            f"테스트 시각: {stamp}\n\n"
            "이 메일이 도착하면 예약 메일 자동화가 정상입니다.",
            queue_on_failure=False,
        )
    except Exception:
        os.unlink(LOCK)
        raise
    print(f"OK: automatic mail sent to {recipient}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
