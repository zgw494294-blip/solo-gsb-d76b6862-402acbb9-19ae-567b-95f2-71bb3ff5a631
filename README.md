# 步道坡线规划台

本地运行的步道纵坡规划小工具：在网页上编辑等间距（1 m）测点的地面标高，
后端用 Python / FastAPI 计算满足坡度与水平段约束的最优方案标高，页面叠画
地面坡线与方案坡线，并列出每段高差、水平段和总调整量。

- 前端：原生 HTML / CSS / JavaScript（Canvas 绘图，无框架、无构建步骤）
- 后端：Python + FastAPI，动态规划求最优解

## 一条命令启动

需要已安装 Docker（含 Compose 插件）。在项目根目录执行：

```bash
docker compose up --build
```

启动后浏览器访问：

```
http://localhost:8000
```

端口为 **8000**（容器内 `8000` 映射到宿主机 `8000`，见 `docker-compose.yml`）。
后台运行可加 `-d`，停止用 `docker compose down`。

## 不使用 Docker 的本地启动方式

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

访问地址同样为 <http://localhost:8000>。

## 规划规则

| 项目 | 规则 |
| --- | --- |
| 测点数量 | 3～16 个，等间距 1 m |
| 地面标高 | 0～200 的整数厘米 |
| 方案标高 | 0～200 的整数厘米 |
| 首尾约束 | 方案首、尾标高必须分别等于地面首、尾标高 |
| 相邻高差 | 相邻方案点高差绝对值 ≤ 8 cm |
| 水平段要求 | 任意连续 5 段中至少有 1 段水平段（相邻方案标高相等） |
| 优化目标 | 总调整量 Σ\|方案标高 − 地面标高\| 最小 |
| 同分裁决 | 取方案标高序列字典序最小者 |

测点不足 6 个（少于 5 段）时，“任意连续 5 段”约束自动不触发。

## 页面与接口说明

- 顶部表格编辑各测点地面标高，可增删测点（受 3～16 个限制）；
  首尾测点的方案标高固定等于地面标高。修改后自动重新计算。
- 图中：**棕色虚线**为地面坡线，**绿色实线**为方案坡线，
  水平段在方案线上以**蓝色点划**叠加标出。
- 结果区列出各点地面/方案标高及差值、各段高差（正为抬升、负为下降）、
  水平段标记、水平段数量、最大相邻高差与总调整量。
- 非法输入（数量越界、非整数、超出 0～200 等）或问题无解时，
  页面以提示条给出中文原因；无解时会区分“坡度约束本身不可达”
  （含首尾高差超限说明）与“水平段约束无法同时满足”。

HTTP 接口（也可直接调用）：

```bash
curl -X POST http://localhost:8000/api/plan \
  -H 'Content-Type: application/json' \
  -d '{"ground":[100,107,114,119,124,130]}'
```

- `200` 且 `feasible=true`：返回 `plan`、`segments`、`horizontal_indices`、
  `total_adjustment` 等。
- `200` 且 `feasible=false`：输入合法但无可行方案，`reason` 说明原因。
- `400`：请求体不是合法 JSON 或缺少 `ground` 字段。
- `422`：输入非法（数量/类型/取值范围），`reason` 说明原因。

## 算法

带“最近 4 段是否水平”位掩码状态的动态规划：

- 状态 `dp[pos][mask][h]`：第 `pos` 点方案标高取 `h`，`mask` 打包此前
  最近 4 段是否水平时，后缀（含本点）的最小调整量；
- 转移枚举下一标高（高差 ≤ 8），当放下的段构成完整的连续 5 段窗口时，
  要求窗口中至少一个水平位；起点之前的“虚拟段”视为水平，
  使不足 5 段时不误触发约束；
- 重建最优路径时每点自低到高取第一个可行且仍为最优的标高，
  即得到同分下字典序最小的方案。

16 个测点的最坏规模单次计算约 0.1 秒（纯 Python）。

## 测试

```bash
pip install pytest httpx
python -m pytest -q
```

测试包含定点用例、非法输入与无解用例，以及对小规模随机地面
（含完整 0～200 值域）的穷举对拍，校验最优值、可行性和字典序裁决。

## 目录结构

```
.
├── app/
│   ├── __init__.py
│   ├── main.py            # FastAPI 入口与 /api/plan
│   ├── planner.py         # 规划算法（动态规划）
│   └── static/
│       └── index.html     # 原生前端页面
├── tests/
│   ├── test_planner.py
│   └── test_api.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```
