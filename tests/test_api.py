"""接口契约、数据库持久化、删除、幂等重试与跨域配置。"""

import csv
import io
import tempfile
import unittest
from pathlib import Path

from src.app import create_app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.config = {
            "TESTING": True,
            "DATABASE_PATH": str(Path(self.directory.name) / "history.db"),
            "CORS_ORIGINS": "http://localhost:8080",
        }
        self.app = create_app(self.config)
        self.client = self.app.test_client()

    def tearDown(self):
        self.directory.cleanup()

    def calculate(self, expression, request_id=None):
        payload = {"expression": expression}
        if request_id is not None:
            payload["request_id"] = request_id
        return self.client.post("/api/calculate", json=payload)

    def test_health_and_calculation(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        response = self.calculate("(1+2)*3")
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(data["result"], "9")
        self.assertEqual(data["expression"], "(1+2)*3")
        self.assertTrue(data["saved"])
        self.assertIn("created_at", data)

    def test_preview_does_not_save(self):
        response = self.client.post("/api/preview", json={"expression": "0.1+0.2"})
        self.assertEqual(response.get_json()["result"], "0.3")
        self.assertFalse(response.get_json()["saved"])
        self.assertEqual(self.client.get("/api/history").get_json()["total"], 0)

    def test_database_survives_new_app_instance(self):
        record = self.calculate("2+3").get_json()
        fresh_app = create_app(self.config)
        history = fresh_app.test_client().get("/api/history").get_json()
        self.assertEqual(history["total"], 1)
        self.assertEqual(history["items"][0]["id"], record["id"])
        self.assertEqual(history["items"][0]["result"], "5")

    def test_deletion_really_removes_database_row(self):
        first = self.calculate("1+2").get_json()["id"]
        second = self.calculate("3+4").get_json()["id"]
        self.assertEqual(self.client.delete(f"/api/history/{first}").status_code, 200)
        fresh_app = create_app(self.config)
        items = fresh_app.test_client().get("/api/history").get_json()["items"]
        self.assertEqual([item["id"] for item in items], [second])
        self.assertEqual(self.client.delete(f"/api/history/{first}").status_code, 404)

    def test_retry_is_idempotent(self):
        first = self.calculate("1+2", "same_request")
        retry = self.calculate("1+2", "same_request")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(first.get_json()["id"], retry.get_json()["id"])
        self.assertEqual(self.client.get("/api/history").get_json()["total"], 1)
        self.assertEqual(self.calculate("2+3", "same_request").status_code, 409)

    def test_pagination_and_literal_search(self):
        for expression in ["1+2", "10+2", "50%", "3+4", "5+6"]:
            self.calculate(expression)
        data = self.client.get("/api/history?page=2&page_size=2").get_json()
        self.assertEqual(data["total"], 5)
        self.assertEqual(len(data["items"]), 2)
        data = self.client.get("/api/history?q=50%25").get_json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["expression"], "50%")
        data = self.client.get("/api/history?q=%27%20OR%201=1").get_json()
        self.assertEqual(data["total"], 0)

    def test_bad_input_does_not_create_records(self):
        for body in [
            {},
            {"expression": 2},
            {"expression": "1+"},
            {"expression": "1/0"},
            {"expression": "1", "request_id": []},
        ]:
            with self.subTest(body=body):
                response = self.client.post("/api/calculate", json=body)
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.get_json()["success"])
        response = self.client.post(
            "/api/calculate", data="not json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/api/history").get_json()["total"], 0)

    def test_request_size_and_bad_pagination(self):
        self.assertEqual(
            self.client.post("/api/calculate", json={"expression": "1" * 20000}).status_code, 413
        )
        for query in ["page=0", "page=no", "page_size=100", "page=-1"]:
            self.assertEqual(self.client.get(f"/api/history?{query}").status_code, 400)

    def test_export_is_parseable_and_escapes_formulas(self):
        self.calculate("-5+2")
        response = self.client.get("/api/history/export")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers["Content-Disposition"])
        rows = list(csv.reader(io.StringIO(response.data.decode("utf-8-sig"))))
        self.assertEqual(rows[0], ["id", "expression", "result", "created_at"])
        self.assertEqual(rows[1][1:3], ["'-5+2", "'-3"])

    def test_cors_preflight_and_unknown_routes(self):
        response = self.client.options(
            "/api/calculate", headers={"Origin": "http://localhost:8080"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "http://localhost:8080")
        self.assertEqual(
            self.client.get(
                "/api/history", headers={"Origin": "https://other.example"}
            ).status_code,
            403,
        )
        response = self.client.get("/api/no-such-route")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.get_json()["success"])
        self.assertEqual(self.client.get("/api/calculate").status_code, 405)


if __name__ == "__main__":
    unittest.main()
