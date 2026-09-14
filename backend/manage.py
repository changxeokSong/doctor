#!/usr/bin/env python
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
