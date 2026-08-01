# BoomyBoom Obsidian Agent

macOS `launchd` 작업이 사용자의 Obsidian 보관함에 기록할 수 있도록 만든 전용 백그라운드 앱이다. Python 전체에 전체 디스크 접근 권한을 주지 않고, 아래의 승인된 작업만 실행한다.

- `/Applications/BoomyBoom/run_daily_brief.sh`
- `/Applications/BoomyBoom/run_kr_brief.sh`
- `/Applications/BoomyBoom-Biz/run_daily_brief.sh`
- `/Applications/BoomyBoom-Biz/run_scout.sh`
- `/Applications/BoomyBoom-Biz/run_weekly_synthesis.sh`

## 빌드

```bash
./build.sh
```

앱은 `/Applications/BoomyBoom Obsidian Agent.app`에 설치된다. 최초 설치 후 macOS 시스템 설정의 개인정보 보호 및 보안, 전체 디스크 접근 권한에서 이 앱을 켜야 한다.

저장소의 `com.boomyboom.*.plist` 파일들은 이 앱을 통해 작업 스크립트를 실행한다. 앱은 정확히 등록된 스크립트 하나만 인수 없이 허용하며, 다른 명령이나 추가 인수는 종료 코드 64로 거부한다.

## 권한 확인

`--smoke`는 실제 브리핑이나 메시지를 발행하지 않고 Obsidian의 `log.md`에 권한 확인 기록만 추가한다.

```bash
"/Applications/BoomyBoom Obsidian Agent.app/Contents/MacOS/boomyboom-obsidian-agent" --smoke
```

`--mail-smoke`는 `.env`의 `MAIL_TO` 주소로 테스트 메일 한 통을 보내 Mail 앱 자동화 권한과 실제 발송 경로를 확인한다. 최초 실행 시 macOS가 Mail 제어 권한을 요청할 수 있다.
10분 안에 다시 실행하면 중복 발송을 막기 위해 전송을 건너뛴다.

```bash
"/Applications/BoomyBoom Obsidian Agent.app/Contents/MacOS/boomyboom-obsidian-agent" --mail-smoke
```

메일 발송이 최종 실패하면 본문은 `logs/mail_queue/`에 로컬로 보관하고, 텔레그램에는 제목과 오류만 알린다.
