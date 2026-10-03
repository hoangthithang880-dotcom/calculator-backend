# 后端代码规范

参考 [PEP 8](https://peps.python.org/pep-0008/) 与 [PEP 257](https://peps.python.org/pep-0257/)，结合小型课程项目作以下约定；不是声称使用了所有企业工程规则。

- UTF-8，4空格缩进；不使用 Tab。顶级定义之间空两行。
- 模块、函数、变量用 `snake_case`，类用 `PascalCase`，常量用 `UPPER_SNAKE_CASE`。
- 标准库导入、第三方导入、本项目相对导入分组；不使用 `import *`。
- 公开模块和关键算法写说明；中文注释解释“为什么”，不逐字复述代码。
- 使用 Black 的100字符目标宽度，允许不能合理拆分的字符串更长。PEP8 默认79字符，此处采用团队一致的宽度。
- Flask 只处理接口；Parser 只处理数学；HistoryRepository 只处理数据库，避免把全部逻辑塞进路由。
- 可预期错误使用 `ExpressionError`，稳定错误码与可读提示分开。不把 traceback 或数据库路径泄露给前端。
- 用户输入不能进入 `eval`、`exec`；SQL 值用 `?` 参数绑定；JSON 验证类型和大小；不得把密钥/数据库上传。
- unittest 用 `test_...` 命名、临时数据库、断言结果与状态码；修复问题时添加相应回归测试。

可选格式工具（不属于运行依赖）：

```bash
python -m pip install black
python -m black --line-length 100 src tests wsgi.py
python -m unittest discover -s tests -v
```

对来源进行引用，不通过改名、混淆、删除注释等方式规避相似度检查。
