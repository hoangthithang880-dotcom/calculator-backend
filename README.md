# 演算台后端

Python + Flask + SQLite 的 JSON API。所有表达式解析、数学计算、历史写入/读取/删除都在本服务完成。配套前端是独立的 `calculator-frontend` 目录，应按作业要求发布为另一个仓库。

## 环境与本地启动

已验证 Python 3.13.15；要求 Python 3.11+。Mac/Linux 在**这个 README 所在目录**运行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m flask --app src.app:create_app run --host 127.0.0.1 --port 5001
```

Mac 如果 `python3` 还是系统 3.9，创建虚拟环境时使用 `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m venv .venv`。VS Code 解释器选本目录 `.venv/bin/python`。

Windows PowerShell：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m flask --app src.app:create_app run --host 127.0.0.1 --port 5001
```

浏览器打开 `http://127.0.0.1:5001/api/health` 应看到 `success: true`。后端没有网页首页，访问 `/` 返回 JSON 404 是正常的。5001 用来避开部分 Mac 上 5000 端口冲突。

## 数据库初始化与环境变量

首次启动自动执行 `src/schema.sql`，默认数据库为本目录 `data/history.db`，无需安装独立数据库软件、手动建表或导入演示数据。

| 变量 | 默认值/用途 |
| --- | --- |
| `DATABASE_PATH` | `data/history.db` 的绝对路径；线上必须设为持久化磁盘路径 |
| `CORS_ORIGINS` | `http://localhost:8080,http://127.0.0.1:8080`；逗号分隔精确的前端来源 |

`.env.example` 只是填写示例，程序**不会自动读取 .env 文件**。在 shell 设置，或在云平台环境变量栏设置：

```bash
export DATABASE_PATH='/absolute/persistent/path/history.db'
export CORS_ORIGINS='https://your-frontend.example'
```

PowerShell 对应 `$env:DATABASE_PATH='C:\calc-data\history.db'`、`$env:CORS_ORIGINS='http://localhost:8080'`。本机一键脚本会设置本地默认值。

成功的“计算并保存”写入一条历史；实时预览不写入。数据库、WAL 文件和虚拟环境已被 `.gitignore` 排除。不要通过删除数据库“清空界面”；单条删除使用指定 id 的 API。

## 接口速查

| 方法和路径 | 作用 |
| --- | --- |
| `GET /api/health` | 服务存活检测 |
| `POST /api/preview` | JSON `{ "expression": "1+2*3" }` → 结果，不保存 |
| `POST /api/calculate` | 同上，可带 `request_id` → 保存并返回记录 |
| `GET /api/history?page=1&page_size=8&q=` | 分页/文字搜索 |
| `DELETE /api/history/123` | 从数据库删除指定 id |
| `GET /api/history/export` | 导出全部历史的 CSV |

请求例子：

```bash
curl -X POST http://127.0.0.1:5001/api/calculate \
  -H 'Content-Type: application/json' \
  -d '{"expression":"(1+2)*3","request_id":"demo_001"}'
```

新记录返回 HTTP 201；同 request_id、同表达式的重试返回同一条记录（200）；编号用于其他表达式返回 409。result 是**字符串**，避免 JavaScript 浮点数二次损失精度。时间为 UTC ISO 8601，前端转换成本地显示。非法表达式/除零返回 400 和中文提示，不写记录。

## 数学与安全边界

自编递归下降解析器，没有 `eval` 或 `exec`。支持 `+-*/()`、小数、科学计数法、一元正负号、`^`、`sqrt(...)` / `√(...)`、后缀 `%`。

先括号，再百分数/幂、一元符号、乘除、加减；幂右结合：`2^3^2=512`，`-2^2=-4`。幂只支持 -100～100 整数指数。百分数按除以100计算，`100+10%=100.1`。隐式乘法、三角函数、变量、代码片段不支持。40 位十进制计算精度，返回最多24位有效数字，不保证任意精度或符号运算。

最大输入256字符、嵌套40层、数值十进制指数绝对值不超过100、JSON16KiB。SQL 使用参数绑定，搜索转义 LIKE 通配符。CORS 限制浏览器来源但**不是认证**；本版所有访客共享同一历史，任何能直接访问 API 的人都可以读写删除，不适用于隐私数据/多租户生产业务。需要私人数据时必须另加账户鉴权、限流与隔离。

## 测试和源码

```bash
python -m unittest discover -s tests -v
```

17 个测试方法覆盖基本/复合计算、错误、安全边界、数据库持久化和实际删除、分页搜索、幂等重试、CSV 与 CORS。测试使用临时数据库，不改正常历史。GitHub Actions 在独立后端仓库执行同一套测试。

```text
src/calculator.py  词法扫描、语法解析、十进制计算、结果格式化
src/app.py         请求验证、路由、CORS、统一错误处理
src/database.py    SQLite 仓储和 CSV
src/schema.sql     自动建表语句
wsgi.py            Gunicorn 部署入口
tests/             unittest 单元与 API 测试
```

## 公开部署

本地 Flask 开发服务器不能作为公网生产服务器。Linux 平台在仓库根目录：

```bash
python -m pip install -r requirements.txt
gunicorn --bind 0.0.0.0:5001 --workers 2 --timeout 30 wsgi:app
```

若平台规定 `$PORT`，把5001改成平台端口（如 `--bind "0.0.0.0:${PORT:-5001}"`）。用平台 HTTPS 或反向代理，配置精确 CORS 和持久磁盘，重启后测试记录仍在。Docker 示例：

```bash
docker build -t calc-notes-api .
docker volume create calc-notes-data
docker run --name calc-notes-api -p 5001:5001 \
  -e CORS_ORIGINS='https://your-frontend.example' \
  -v calc-notes-data:/data calc-notes-api
```

Docker 方案需自己提供 HTTPS；命名卷不能换成容器临时目录。SQLite/WAL 适合课程的单主机小规模并发，不要让多主机副本共用网络文件系统上的数据库。在线 URL 由部署完成后填写，此包没有声称已经部署。

代码规范：[codestyle.md](codestyle.md)。工具依据：[Flask 部署文档](https://flask.palletsprojects.com/en/stable/deploying/)、[Python decimal](https://docs.python.org/3/library/decimal.html)、[sqlite3](https://docs.python.org/3/library/sqlite3.html)。AI 辅助编写/测试；提交者需遵循课程披露规则，理解与自主核验后使用。
