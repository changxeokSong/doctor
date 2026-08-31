#!/usr/bin/env python
"""Django manage.py. 항상 저장소 루트(doctor/)를 작업 디렉터리로 두고 실행한다
(예: `python backend/manage.py runserver`) — app/config.py의 엑셀 경로가 상대경로라서
그래야 데이터 파일을 찾는다. sys.path에 저장소 루트를 넣는 건 config.settings에서 처리한다."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    sys.path.insert(0, os.path.dirname(__file__))
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django를 import할 수 없습니다. django_backend conda 환경이 활성화됐는지 확인하세요."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
