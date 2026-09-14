#!/usr/bin/env bash
# 启动管风琴机械传动放样台：http://127.0.0.1:5000
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv --without-pip .venv
  python3 /tmp/get-pip.py 2>/dev/null || .venv/bin/python /tmp/get-pip.py
  .venv/bin/pip install flask
fi
exec .venv/bin/python -m organlab.app "$@"
