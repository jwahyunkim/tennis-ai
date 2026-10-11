# Colab에서 AI 실험 준비

2026-10-11 기준. 현재 제공하는 것은 **환경 점검 노트북**입니다. 모델 추론·학습,
영상 분석·3D 생성·운영 API 연동은 아직 구현하지 않았습니다.

## 환경별 역할

| 환경 | 용도 |
| --- | --- |
| Codespaces | 앱·백엔드·분석 코드 작성, 가벼운 검증 |
| Colab | 모델 후보를 정한 뒤 샘플 추론·품질·처리시간·메모리 실험 |
| 데스크탑 | Android 앱 빌드·실기기 테스트 |
| 향후 운영 환경 | 사용자 영상의 자동 처리. 공급자와 예산은 미정 |

## 준비 노트북 실행

1. [Colab에서 열기](https://colab.research.google.com/github/jwahyunkim/tennis-ai/blob/feature/video-platform/notebooks/colab_setup.ipynb).
   소스는 [colab_setup.ipynb](../notebooks/colab_setup.ipynb)입니다. 링크는 현재 작업 브랜치를
   가리키므로 브랜치 삭제·이름 변경 시 갱신합니다.
2. Python 런타임에 연결합니다. 준비 단계는 CPU로 충분합니다. 모델 실험에서 필요한 경우
   런타임 유형을 GPU로 변경하고 첫 셀부터 다시 실행합니다.
3. 셀을 위에서부터 실행합니다. Python·설치 패키지 버전, NVIDIA GPU 조회 상태,
   임시 실험 폴더와 `outputs/environment.json` 경로가 표시됩니다.
4. 필요한 보고서는 Colab 파일 패널에서 다운로드합니다. 노트북을 수정했다면 개인 사본을
   저장하고, 저장소 반영 전 코드와 비어 있는 출력을 검토합니다.

이 노트북은 Python 표준 라이브러리만 사용합니다. 패키지를 설치하거나 가중치·영상을
다운로드하지 않습니다. `null` 패키지 버전은 미설치를 뜻하고, `not_detected`는
`nvidia-smi`가 없음을 뜻합니다. `query_failed`는 장치 조회 실패이며 모델 오류가 아닙니다.
GPU 조회 성공은 프레임워크의 GPU 사용이나 모델 실행 성공을 보장하지 않습니다.

## 파일과 Git 관리

노트북은 Colab의 `/content` 아래(일반 로컬 실행 시 시스템 임시 경로)에 고유한
`tennis-ai-*` 폴더를 만들고 `inputs/`, `models/`, `outputs/`로 구분합니다.
세 폴더 중 `outputs/`에 환경 JSON만 쓰며 샘플·가중치는 아직 취급하지 않습니다.
런타임 디스크는 임시이므로 필요한 결과는 종료 전 데스크탑 또는 권한을 제한한 외부
저장소에 보존합니다. Google Drive 연결은 이 준비 노트북에 포함하지 않습니다.

Git에는 노트북·분석 소스·의존성 명세·비개인 평가 요약만 보관합니다. 저장소 안에서
임시 실험이 필요하면 Git에서 제외되는 `notebooks/local/` 아래를 사용합니다.
`.ipynb_checkpoints/`도 제외합니다. 영상·개인 결과·가중치를 다른 경로에 저장한다고
자동 제외되는 것은 아니므로 커밋 대상을 확인합니다.

노트북 출력은 `.gitignore`로 제거되지 않습니다. 커밋 전 코드 셀의 `outputs`를 비우고
`execution_count`를 `null`로 되돌리며, 첨부 이미지·토큰·개인 경로가 없는지 검토합니다.
현재 배포한 노트북에는 실행 출력이나 사용자 데이터가 없습니다.

## 실제 분석으로 이어가기

먼저 [T-02~T-04](project-status.md)의 분석 범위·데이터 사용 기준·모델 라이선스를 정합니다.
그다음 해당 모델의 의존성과 버전, 가중치 출처/버전, 입력 형식, 전후처리를 기록하고
샘플 추론을 추가합니다. 처음부터 학습이 필요한지는 사전학습 모델 결과를 보고 판단합니다.

모델 구현은 노트북에만 묶지 않고 재사용 가능한 Python 모듈로 분리합니다. 이후 서비스
연결에서는 기존 `backend/services/media.py`의 `BodyReconstructor` 경계를 검토합니다.
현재 계약은 GLB 결과용이며, 2D 지표·외부 GPU 비동기 작업은 별도 계약 검토가 필요합니다.
이 준비로 backend 의존성이나 worker 동작은 바뀌지 않습니다.

Colab은 초기 실험용입니다. GPU 종류·사용량·실행 시간은 가변적이고 런타임이 삭제될 수
있으므로 상시 사용자 분석 서비스로 전제하지 않습니다. 유료 요금제 선택도 아직 없습니다.
2026-10-11 확인: [Colab 공식 FAQ](https://research.google.com/colaboratory/faq.html),
[Jupyter 노트북 형식](https://nbformat.readthedocs.io/en/latest/format_description.html).
