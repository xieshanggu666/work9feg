# 📝 在线考试与题库管理系统

基于 **FastAPI + Vue 3 + TypeScript** 的在线考试平台，支持题库管理、智能组卷、在线考试、自动评分、成绩统计与证书发放。

## ✨ 功能特性

### 题库管理
- 6 种题型：单选、多选、判断、填空、简答、编程
- 科目 / 知识点树 / 标签体系
- 难度分级（1-5）、区分度统计
- 单题 / 批量导入

### 智能组卷
- 按 **知识点权重** 分配题目
- 按 **难度分布** 抽取题目
- 按 **题型分布** 约束题数
- 自动校验总分并给出告警

### 考试与答题
- 考试生命周期：草稿 → 发布 → 结束
- 题目乱序、选项乱序
- 限时考试 + 倒计时自动交卷
- **防作弊**：切屏检测（超限警告 / 强制交卷）、答题用时异常检测、同 IP 多账号检测

### 自动评分
- 单选 / 判断：自动比对
- 多选：全对满分、漏选部分分、错选零分
- 填空：多标准答案匹配
- 简答：关键词命中率给分
- 编程：标记待人工评测

### 成绩统计
- 考试整体统计（平均分、及格率、分数分布）
- 单题统计（正确率、实际难度、区分度）
- 排名与百分位、排行榜
- 通过考试自动生成证书

### 考试预约与补考
- **管理员**：配置考试时段（时间窗口 + 名额），可开放/关闭、调整名额
- **学生**：选择时段提交首考/补考申请，可查看审核进度、取消预约
- **教师**：审核预约申请（通过即占用名额，驳回可重新申请）
- **预约状态驱动开考资格**：仅"已通过且在时段窗口内"才能开考，开考后预约置为已使用
- **次数限制**：每门考试可配置最大次数（`max_attempts`，1=仅首考，>1 支持补考）；
  时段结束未考自动判定**缺考**并消耗一次机会
- **成绩联动**：统计含参考人数（去重）、到考率、缺考、首考/补考人次与补考通过率；
  排名/排行榜按每人**最佳成绩**计算；补考通过**自动发证**（取最高成绩）

## 🧱 技术栈

| 端 | 技术 |
|----|------|
| 前端 | Vue 3（`<script setup>`）+ TypeScript + Vite + Vue Router + Pinia + Axios |
| 后端 | FastAPI / SQLAlchemy 2.0 / Pydantic v2 / python-jose / bcrypt |
| 数据库 | SQLite |

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+（推荐 20+）

### 1. 安装依赖

```bash
# 后端依赖
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt

# 根目录（concurrently）+ 前端依赖（一条命令会同时安装）
npm install
npm --prefix frontend install
```

### 2. 初始化数据库（首次运行）

含示例数据：4 用户、1 科目、6 知识点、23 题、1 场已发布考试（需预约、允许 1 次补考），
附 2 个考试时段与 2 条示例预约（student1 已审核通过、student2 待审核）。

```bash
npm run init-db
# 等价于：python scripts/init_db.py
```

### 3. 同时启动前后端（开发模式）

```bash
npm run dev
```

该命令通过 `concurrently` 同时启动：

| 服务 | 地址 | 说明 |
|------|------|------|
| 后端 FastAPI | http://127.0.0.1:8000 | 开启 `--reload`，接口文档 `/docs` |
| 前端 Vite | http://127.0.0.1:5173 | HMR 热更新，`/api` 自动代理到后端 |

浏览器访问 **http://127.0.0.1:5173** 即可。

也可以分别启动：

```bash
npm run dev:backend     # 仅后端 :8000
npm run dev:frontend    # 仅前端 :5173
```

### 示例账号

| 角色 | 账号 | 密码 |
|------|------|------|
| 管理员 | admin | 123456 |
| 教师 | teacher | 123456 |
| 学生 | student1 / student2 | 123456 |

## 📦 生产部署

```bash
# 1. 构建前端（产物输出到 frontend/dist）
npm run build

# 2. 启动后端，FastAPI 会自动托管 frontend/dist 下的 SPA
npm start
# 等价于：python -m uvicorn app.main:app --port 8000
```

访问 http://127.0.0.1:8000 即为前端页面；非 API 路径统一回退到 `index.html`（支持前端路由刷新）。
生产环境建议通过 Nginx 等反向代理并配置 HTTPS。

## 🧪 运行测试

```bash
npm test
# 等价于：pytest tests/ -v
```

## 📁 目录结构

```
exam_system/
├── app/                     # FastAPI 后端
│   ├── main.py              # 入口（API 路由 + CORS + 生产环境 SPA 托管）
│   ├── core/                # 配置 / 数据库 / 安全 / 依赖
│   ├── models/              # SQLAlchemy 模型（12 张表）
│   ├── schemas/             # Pydantic 校验
│   ├── services/            # 业务逻辑（组卷 / 评分 / 统计 / 防作弊）
│   ├── api/                 # REST 接口
│   └── utils/
├── frontend/                # Vue 3 + TypeScript 前端
│   ├── src/
│   │   ├── api/             # Axios 封装与各模块接口
│   │   ├── stores/          # Pinia（登录态）
│   │   ├── router/          # Vue Router（含登录守卫）
│   │   ├── layouts/         # 带顶部导航的布局
│   │   ├── views/           # 登录/仪表盘/题库/考试/答题/结果/统计/证书
│   │   ├── types/           # 全局 TS 类型
│   │   └── styles/
│   ├── vite.config.ts       # /api 代理到 127.0.0.1:8000
│   └── package.json
├── scripts/init_db.py       # 初始化脚本
├── tests/                   # 单元测试
├── package.json             # 根脚本：dev / build / start / test
└── data/                    # SQLite 数据库文件
```

## 🔌 主要 API

| 模块 | 接口 |
|------|------|
| 认证 | `POST /api/auth/login` |
| 题库 | `GET/POST /api/questions`、`/api/questions/subjects`、`/api/questions/knowledge-points`、`/api/questions/tags` |
| 考试 | `GET/POST /api/exams`、`POST /api/exams/papers/smart-generate` |
| 答题 | `POST /api/attempts/{exam_id}/start`、`POST /api/attempts/{attempt_id}/submit`、`POST /api/attempts/{attempt_id}/screen-switch` |
| 统计 | `GET /api/grades/stats/{exam_id}`、`/api/grades/rank/{exam_id}`、`/api/grades/leaderboard/{exam_id}`、`/api/grades/certificates` |
| 预约补考 | 时段：`POST/GET /api/exams/{id}/slots`、`PUT/DELETE /api/slots/{id}`（管理员）；申请：`POST /api/bookings`、`GET /api/bookings/my`、`POST /api/bookings/{id}/cancel`（学生）；审核：`GET /api/bookings`、`POST /api/bookings/{id}/review`（教师/管理员）；资格：`GET /api/exams/{id}/eligibility` |

完整接口文档：启动后访问 `http://127.0.0.1:8000/docs`（Swagger UI）。
