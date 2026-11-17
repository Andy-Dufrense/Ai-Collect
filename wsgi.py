"""Gunicorn 生产环境入口。"""

from app import app


# Gunicorn 通过 “wsgi:app” 找到 Flask 应用。
application = app
