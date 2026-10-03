"""Flask API：计算、预览、历史查询、单条删除和 CSV 导出。"""

import os
import re
import sqlite3
from pathlib import Path

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from .calculator import ExpressionError, evaluate_expression, format_number
from .database import HistoryRepository


def create_app(config=None):
    app = Flask(__name__, static_folder=None)
    app.config.from_mapping(
        DATABASE_PATH=os.environ.get(
            "DATABASE_PATH", str(Path(__file__).parent.parent / "data" / "history.db")
        ),
        CORS_ORIGINS=os.environ.get("CORS_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080"),
        MAX_CONTENT_LENGTH=16 * 1024,
    )
    if config:
        app.config.update(config)
    app.json.ensure_ascii = False
    repository = HistoryRepository(app.config["DATABASE_PATH"])
    app.extensions["history"] = repository
    origins = {
        origin.strip().rstrip("/")
        for origin in app.config["CORS_ORIGINS"].split(",")
        if origin.strip()
    }

    @app.before_request
    def check_origin():
        origin = request.headers.get("Origin")
        if origin and origin not in origins:
            return (
                jsonify(
                    success=False,
                    code="ORIGIN_NOT_ALLOWED",
                    message="该网页地址尚未加入后端允许列表",
                ),
                403,
            )

    @app.after_request
    def response_headers(response):
        origin = request.headers.get("Origin")
        if origin in origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def input_expression():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ExpressionError("请使用 JSON 对象发送表达式", "INVALID_INPUT")
        expression = data.get("expression")
        if not isinstance(expression, str):
            raise ExpressionError("expression 必须是文字", "INVALID_INPUT")
        # 前后空白无需存储，中间空白由解析器识别。
        expression = expression.strip()
        return expression, data

    @app.get("/api/health")
    def health():
        return jsonify(success=True, name="演算台", status="ok")

    @app.post("/api/preview")
    def preview():
        expression, _ = input_expression()
        result = format_number(evaluate_expression(expression))
        return jsonify(success=True, expression=expression, result=result, saved=False)

    @app.post("/api/calculate")
    def calculate():
        expression, data = input_expression()
        request_id = data.get("request_id")
        if request_id is not None and (
            not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id)
        ):
            raise ExpressionError("request_id 格式不正确", "INVALID_INPUT")
        result = format_number(evaluate_expression(expression))
        record, created = repository.save(expression, result, request_id)
        return jsonify(success=True, **record, saved=True), 201 if created else 200

    @app.get("/api/history")
    def history():
        query = request.args.get("q", "").strip()
        try:
            page = int(request.args.get("page", "1"))
            page_size = int(request.args.get("page_size", "8"))
        except ValueError as error:
            raise ExpressionError("分页参数必须是整数", "INVALID_INPUT") from error
        if not 1 <= page <= 1000000 or not 1 <= page_size <= 50 or len(query) > 256:
            raise ExpressionError("分页或搜索参数超出允许范围", "INVALID_INPUT")
        return jsonify(success=True, **repository.list(query, page, page_size))

    @app.delete("/api/history/<int:record_id>")
    def delete_history(record_id):
        if not repository.delete(record_id):
            return (
                jsonify(success=False, code="NOT_FOUND", message="这条历史记录不存在或已被删除"),
                404,
            )
        return jsonify(success=True, deleted_id=record_id)

    @app.get("/api/history/export")
    def export_history():
        return app.response_class(
            repository.export(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=calculation-history.csv"},
        )

    @app.errorhandler(ExpressionError)
    def expression_error(error):
        status = 409 if error.code == "REQUEST_CONFLICT" else 400
        return (
            jsonify(success=False, code=error.code, message=error.message, position=error.position),
            status,
        )

    @app.errorhandler(sqlite3.Error)
    def database_error(error):
        app.logger.error("Database operation failed: %s", type(error).__name__)
        return (
            jsonify(
                success=False, code="DATABASE_UNAVAILABLE", message="记录服务暂时不可用，请稍后重试"
            ),
            503,
        )

    @app.errorhandler(HTTPException)
    def http_error(error):
        messages = {404: "接口不存在", 405: "请求方式不正确", 413: "请求内容过大"}
        return (
            jsonify(
                success=False, code="HTTP_ERROR", message=messages.get(error.code, "请求无法处理")
            ),
            error.code,
        )

    @app.errorhandler(Exception)
    def unexpected_error(error):
        app.logger.exception("Unexpected server error")
        return jsonify(success=False, code="SERVER_ERROR", message="服务发生错误，请稍后重试"), 500

    return app
