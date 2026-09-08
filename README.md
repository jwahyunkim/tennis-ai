# Tennis AI

사용자가 테니스 영상을 올리고, 이후 AI가 움직임과 체형을 반영한 3D 모델을 생성하는
Flutter Android · FastAPI · PostgreSQL 프로젝트입니다.

## 현재 상태

| 영역 | 준비 상태 |
| --- | --- |
| Android | Flutter 3.44.7 / Dart 3.12.2, Android SDK 36, JDK 17 |
| Flutter 앱 | Material 3·Riverpod, 인증·프로필·영상 업로드·목록·재생·작업 상태·3D 결과 화면. 앱은 저장소 루트에 위치 |
| Backend 환경 | Python 3.12 가상환경, FastAPI/Uvicorn, 비동기 SQLAlchemy/asyncpg, Alembic, 테스트·린트 도구 |
| Backend API | 인증·세션·사용자 권한, 영상 저장·조회·삭제, 작업 재시도·취소, GLB 결과 계약, Alembic 마이그레이션 |
| PostgreSQL | Docker Compose로 실행하는 PostgreSQL 18.6, 상태 확인 및 데이터 볼륨 |
| 영상 처리 | 별도 worker의 FFprobe 검증, 크기·길이·사용자 저장 용량 제한, 로컬/S3 저장소 |
| 개발·운영 | Dev Container, GitHub Actions CI, 비루트 Docker 이미지, 요청 로그·상태 검사, 백업·복원 |

현재 구현은 **AI 학습·추론을 연결하기 전의 사용자·영상·작업·결과 관리 플랫폼**입니다.
worker는 영상 메타데이터를 검증한 뒤 작업을 `awaiting_model`로 전환합니다.
현재 사용자 체형·움직임을 추정하거나 3D 모델을 생성하지 않습니다. 모델이 연결되지 않은
영상에는 대기 상태를 표시하며 샘플 모델을 사용자 분석 결과처럼 보여주지 않습니다.
관절·근육·선수 동작 분석 파라미터와 학습 데이터·모델은 후속 단계에서 결정합니다.

## 개발환경 시작

GitHub Codespaces 또는 이 저장소의 Dev Container를 사용합니다.
컨테이너 생성 시 의존성을 설치하고 PostgreSQL 시작 후 Alembic 마이그레이션을 적용합니다.
이후 컨테이너를 시작할 때도 PostgreSQL의 준비 상태를 확인합니다.

이미 열린 Codespace에서 설정을 적용하거나 의존성을 다시 설치하려면 저장소 루트에서 실행합니다.

```bash
bash .devcontainer/scripts/setup-development.sh
source .devcontainer/scripts/dev-env.sh
source backend/.venv/bin/activate
```

설치 스크립트는 기존 `pubspec.lock`과 Python 의존성 잠금 파일을 사용합니다.
`infra/.env`가 없을 때만 임의의 DB 비밀번호를 생성하며 기존 설정은 보존합니다.
가상환경과 실제 `.env` 파일은 Git에서 제외됩니다.
Dev Container 설정 자체를 변경한 경우 이후 새 컨테이너에도 적용하려면 Rebuild Container를 사용합니다.
영상 검사에는 `ffprobe`가 필요합니다. 새 Dev Container에는 FFmpeg가 포함되며,
기존 컨테이너에 없다면 OS 패키지 `ffmpeg`를 설치합니다.

## 검증과 Android 빌드

```bash
bash .devcontainer/scripts/check-development.sh
flutter build apk --debug
```

검증 스크립트는 Flutter 정적 분석·테스트, ShellCheck, Python 의존성·린트·포맷 검사,
Backend 단위·HTTP·PostgreSQL 통합 테스트와 Alembic 모델 차이를 확인합니다.
PostgreSQL 시작과 개발 DB 마이그레이션은 먼저 setup 또는 명시적 `upgrade head`로 적용합니다.
검증 스크립트는 개발 DB 스키마를 변경하지 않으며, 테스트는 API 서버를 계속 실행하지 않습니다.
GitHub Actions도 별도 `tennis_ai_test` DB로 Backend를 검증하고 Flutter 분석·테스트와
Android debug APK 빌드를 실행합니다. Actions 버전은 확인한 커밋으로 고정합니다.
로컬 도메인 통합 테스트도 `tennis_ai_test`를 생성·마이그레이션한 뒤 사용합니다.
`POSTGRES_TEST_DB`로 바꿀 수 있으며 `_test`로 끝나는 별도 DB만 허용합니다.

APK 결과물은 `build/app/outputs/flutter-apk/app-debug.apk`입니다.
기기에서 실행하려면 `flutter devices`로 연결을 확인한 후 `flutter run -d <device-id>`를 사용합니다.
Codespaces에는 Android 기기나 에뮬레이터가 기본 연결되지 않습니다.
Android 개발에는 Chrome 및 Linux 데스크톱용 `flutter doctor` 경고 해결이 필요하지 않습니다.

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

`API_BASE_URL`은 `/api/v1`을 제외한 API 원점 주소입니다. 위 주소는 Android
에뮬레이터에서 개발 머신에 접근할 때 사용합니다. 실제 기기에서는 기기가 접근 가능한
API 주소를 지정합니다. Release 앱은 HTTPS API 주소를 요구합니다.

## Backend API 실행

저장소 루트에서 실행합니다. 개발 DB 설정은 기존 `infra/.env`를 재사용합니다.

```bash
bash .devcontainer/scripts/start-services.sh
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
backend/.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload --no-access-log
```

별도 터미널에서 `backend/.venv/bin/python -m backend.worker`를 실행합니다.
API 문서는 `http://127.0.0.1:8000/docs`에서 확인합니다.
기능 API는 `/api/v1` 아래에 있으며 인증 이후 Bearer 토큰을 사용합니다.

| 경로 | 정상 응답 | 용도 |
| --- | --- | --- |
| `GET /health` | `200 {"status":"ok"}` | DB 접속 없이 서버 응답 확인 |
| `GET /health/ready` | `200 {"status":"ok","database":"ok"}` | 실제 PostgreSQL 쿼리 확인 |

DB 장애나 제한 시간 초과 시 readiness는
`503 {"status":"unavailable","database":"unavailable"}`를 반환합니다.
접속 오류와 비밀번호는 응답에 포함하지 않습니다.

환경변수는 `infra/.env`보다 우선합니다. `POSTGRES_PASSWORD`는 필수이며,
`POSTGRES_HOST`(기본 `127.0.0.1`), `POSTGRES_PORT`(기본 `5432`),
`POSTGRES_DB`·`POSTGRES_USER`(기본 `tennis_ai`),
`DATABASE_TIMEOUT_SECONDS`(기본 5초, 0초 초과·60초 이하)를 설정할 수 있습니다.
배포 환경에서는 환경변수 또는 비밀 관리 도구로 값을 주입합니다.
영상 기본 저장 경로는 `~/.local/share/tennis-ai/media`로 저장소 밖에 있습니다.
파일당 250 MiB, 최대 120초, 사용자별 원본 영상 2 GiB 제한이 기본값입니다. 세션 유효 기간,
저장 용량과 S3 저장소 등 추가 설정은 [운영 가이드](docs/operations.md)를 참고합니다.

DB 없이 실행하는 Backend 테스트와 실제 DB를 포함하는 테스트를 구분합니다.

```bash
backend/.venv/bin/python -m pytest -c backend/pyproject.toml
RUN_DB_TESTS=1 backend/.venv/bin/python -m pytest -c backend/pyproject.toml
```

HTTP 라우터, 서비스, 저장소, 스키마와 공통 설정은 `backend/` 아래에서 분리합니다.
DB 엔진은 앱 수명 동안 재사용하고 종료 시 해제합니다. 요청별 세션은 종료 시 닫으며,
쓰기 작업의 트랜잭션과 커밋은 서비스에서 명시적으로 관리합니다.
앱 시작 시 테이블을 생성하거나 마이그레이션을 실행하지 않습니다.

## 데이터베이스 마이그레이션

Alembic은 API와 같은 DB 설정과 `backend/models/base.py`의 메타데이터를 사용합니다.
사용자·세션·영상·작업·결과 모델을 마이그레이션으로 관리합니다. 새 모델은
`backend/models/__init__.py`에서 가져와 메타데이터에 등록합니다. 저장소 루트에서 상태를 확인합니다.

```bash
backend/.venv/bin/alembic -c backend/alembic.ini current
backend/.venv/bin/alembic -c backend/alembic.ini check
```

모델 변경 후 `revision --autogenerate -m "describe schema change"`로 리비전을 생성하고,
생성된 내용을 검토한 뒤 `upgrade head`로 적용합니다. 두 명령 모두 위와 같이
`backend/.venv/bin/alembic -c backend/alembic.ini` 뒤에 붙여 실행합니다.
운영 스키마 변경은 검토한 Alembic 리비전으로만 수행합니다.

## PostgreSQL 관리

```bash
# 시작 또는 상태 확인
bash .devcontainer/scripts/start-services.sh
docker compose --env-file infra/.env -f infra/compose.yaml ps

# 컨테이너에 포함된 psql로 접속
docker compose --env-file infra/.env -f infra/compose.yaml exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'

# 데이터 볼륨을 유지하며 중지
docker compose --env-file infra/.env -f infra/compose.yaml stop
```

접속 주소는 `127.0.0.1:5432`이며 DB 이름·사용자·비밀번호는 `infra/.env`에 있습니다.
포트가 겹치면 `POSTGRES_PORT`를 변경하고 시작 스크립트를 다시 실행합니다.
Compose 데이터 볼륨은 서비스 재시작 시 유지됩니다. `down --volumes`는 데이터를 삭제합니다.
Codespace 삭제나 컨테이너 재생성 전에는 필요한 개발 데이터를 별도로 백업합니다.
DB 초기화 이후 `.env` 비밀번호만 바꾸면 기존 DB 계정의 비밀번호는 바뀌지 않습니다.

## 전체 서비스와 운영

`infra/.env`를 준비한 뒤 API·worker·마이그레이션을 함께 실행합니다.

```bash
docker compose --env-file infra/.env -f infra/compose.yaml --profile app up -d --build
docker compose --env-file infra/.env -f infra/compose.yaml --profile app ps
```

PostgreSQL 준비 → 일회성 마이그레이션 → API·worker 순서로 실행합니다.
API는 `127.0.0.1:8000`에 연결되며 영상은 별도 `media_data` 볼륨에 보존합니다.
[운영 가이드](docs/operations.md)에 갱신·로그·백업·복원·Android 배포 서명 절차가 있습니다.
공개 운영 시 선택한 호스트의 HTTPS 프록시·비밀·백업·알림을 연결합니다.
현재 저장소 작업으로 특정 클라우드 리소스가 생성되거나 Play Store에 앱이 게시되지는 않습니다.

## Python 의존성 변경

Python 3.12에서 `backend/requirements.in` 또는 `backend/requirements-dev.in`을 수정한 뒤
저장소 루트에서 해시가 포함된 잠금 파일을 다시 생성합니다.

```bash
backend/.venv/bin/python -m piptools compile --generate-hashes --allow-unsafe --strip-extras \
  --no-emit-index-url --no-emit-trusted-host \
  --output-file=backend/requirements.txt backend/requirements.in
backend/.venv/bin/python -m piptools compile --generate-hashes --allow-unsafe --strip-extras \
  --no-emit-index-url --no-emit-trusted-host \
  --output-file=backend/requirements-dev.txt backend/requirements-dev.in
bash .devcontainer/scripts/setup-development.sh
```

개발 의존성은 런타임 잠금 파일을 제약 조건으로 사용합니다.
새 버전으로 올리는 경우 해당 패키지에 `--upgrade-package <name>`을 명시하고 두 잠금 파일을 검토합니다.

설정 근거: [Flutter PATH 설정](https://docs.flutter.dev/install/add-to-path),
[Dev Container 생명주기](https://containers.dev/implementors/json_reference/),
[PostgreSQL 공식 이미지](https://hub.docker.com/_/postgres),
[pip-tools 의존성 잠금](https://pip-tools.readthedocs.io/en/stable/).

Backend 구성 근거: [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/),
[SQLAlchemy 비동기 I/O](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html),
[Pydantic 환경설정](https://docs.pydantic.dev/latest/concepts/pydantic_settings/),
[Alembic 비동기 구성](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic).
