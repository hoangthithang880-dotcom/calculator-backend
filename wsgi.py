"""生产服务器入口：gunicorn wsgi:app。"""

from src.app import create_app

app = create_app()
