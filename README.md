# FundVision - 基金估值与回撤分析系统

<div align="center">

**基于 Flask 的智能基金分析平台**

实时估值 · 回撤分析 · 净值图表 · AI 解析 · 多主题适配

</div>

---

## ✨ 核心功能

### 📊 数据分析
- **实时估值** - 估算基金当日涨跌幅，掌握盘中动态
- **90日高点回撤** - 分析基金距离近期高点的回撤幅度
- **风险指标** - 夏普比率、年化波动率、最大回撤、同类排名
- **净值走势图表** - ECharts 可视化历史净值曲线，支持 1/2/3/6/12 个月周期切换，区间统计一目了然

### 🤖 智能交互
- **AI 智能解析** - 自然语言输入，自动识别基金代码和持仓
- **模糊搜索** - 支持代码/名称/拼音搜索，单字符也能快速定位
- **混合输入** - AI 解析与手动搜索无缝协作

### � 用户体验
- **深色/浅色主题** - 一键切换，平滑过渡动画
- **响应式设计** - 完美适配桌面端与移动端
- **Toast 通知** - 优雅的消息提示系统
- **本地缓存** - 基金列表自动保存，刷新不丢失

### ⚡ 性能表现
- **并行分析** - 线程池并行处理，多基金分析速度倍增
- **实时指数** - 左侧边栏显示主要指数涨跌幅

---

## 🛠 技术栈

| 类别 | 技术 |
|------|------|
| 后端 | Flask + Flask-CORS + Flask-Limiter |
| 前端 | 原生 HTML + Tailwind CSS + GSAP + ECharts |
| 数据 | akshare + pandas |
| AI | DeepSeek / OpenAI / Claude / Gemini / Ollama |

---

## 🚀 快速开始

### 1. 安装依赖

```bash
git clone https://github.com/你的用户名/fund.git
cd fund
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
AI_PROVIDER=deepseek
AI_API_KEY=your_api_key_here
```

### 3. 启动服务

**双击 `run.bat`** 自动启动后端并打开前端页面

或手动运行：

```bash
python app.py
```

- 后端 API: `http://localhost:5000`
- 前端界面: 打开 `index.html`

---

## 📖 使用指南

### AI 智能解析
粘贴任意格式的持仓描述，AI 自动识别：

```
易方达蓝筹精选混合 110011 10000元
我买了20000块的白酒基金，代码是012414
012414,15000
```

### 基金详情
点击基金卡片进入详情页，查看：
- 📋 持仓明细与涨跌幅
- 📈 净值走势图表（支持多周期切换）
- 📊 区间最高/最低净值、收益率统计

### 主题切换
点击顶部按钮切换深色/浅色模式，设置自动保存

---

## 🔌 API 接口

### 接口列表

| 接口 | 方法 | 说明 | 限流 |
|------|------|------|------|
| `/api/health` | GET | 健康检查 | 无 |
| `/api/search_fund` | GET | 基金搜索（支持代码/名称/拼音） | 60/min |
| `/api/fund_info/<code>` | GET | 基金基本信息 | 60/min |
| `/api/parse_funds` | POST | AI 解析自然语言 | 10/min |
| `/api/fund_analysis` | POST | 完整分析（估值+回撤+风险指标） | 20/min |
| `/api/estimate` | POST | 仅估值 | 30/min |
| `/api/drawdown` | POST | 仅回撤分析 | 30/min |
| `/api/get_indices` | GET | 实时指数涨跌幅 | 30/min |
| `/api/get_fund_detail` | GET | 基金持仓详情（含股票涨跌幅） | 10/min |
| `/api/get_nav_history` | GET | 单只基金历史净值数据 | 30/min |
| `/api/get_nav_history_batch` | GET | 批量获取历史净值数据（最多4只） | 20/min |

---

### 1. 健康检查

```bash
GET /api/health
```

**响应示例：**
```json
{
  "status": "ok",
  "version": "6.4 Compare-Edition",
  "time": "2026-02-12T10:30:00",
  "modules": ["estimate", "drawdown", "fund_analysis", "ai_parse", "fund_search", "nav_history", "nav_history_batch"],
  "default_window": "90d",
  "ai_enabled": true,
  "ai_provider": {"provider": "deepseek", "model": "deepseek-chat", "configured": true}
}
```

---

### 2. 基金搜索

```bash
GET /api/search_fund?keyword=白酒&limit=10
```

**参数：**
- `keyword` (必填): 搜索关键词，至少2个字符
- `limit` (可选): 返回数量，默认10，最大20

**响应示例：**
```json
{
  "success": true,
  "keyword": "白酒",
  "results": [
    {"code": "161725", "name": "招商中证白酒指数(LOF)A", "pinyin": "ZSZSBZJ", "type": "股票型"},
    {"code": "012414", "name": "招商中证白酒指数C", "pinyin": "ZSZSBZJ", "type": "股票型"}
  ],
  "count": 2
}
```

---

### 3. 基金基本信息

```bash
GET /api/fund_info/110011
```

**响应示例：**
```json
{
  "success": true,
  "fund": {
    "code": "110011",
    "name": "易方达中小盘混合",
    "pinyin": "YFDZXP",
    "type": "混合型"
  }
}
```

---

### 4. AI 解析自然语言

```bash
POST /api/parse_funds
Content-Type: application/json

{"text": "易方达蓝筹10000元，012414白酒基金20000块"}
```

**响应示例：**
```json
{
  "success": true,
  "funds": [
    {"code": "005827", "name": "易方达蓝筹精选混合", "holding": 10000},
    {"code": "012414", "name": "招商中证白酒指数C", "holding": 20000}
  ],
  "count": 2
}
```

---

### 5. 基金完整分析

```bash
POST /api/fund_analysis
Content-Type: application/json

{
  "funds": [
    {"code": "110011", "name": "易方达蓝筹", "holding": 10000}
  ]
}
```

**响应示例：**
```json
{
  "summary": {
    "total_funds": 1,
    "analyzed_successfully": 1,
    "timestamp": "2026-02-12T10:30:00"
  },
  "detailed_results": [{
    "fund_code": "110011",
    "fund_name": "易方达蓝筹精选混合",
    "holding": 10000,
    "real_time_estimate": {
      "today_change_pct": 0.25,
      "estimated_nav": 5.35,
      "market": "A股",
      "benchmark": "沪深300",
      "update_time": "14:30:00"
    },
    "historical_drawdown": {
      "yesterday_nav": 5.34,
      "rolling_high_90d": 5.65,
      "high_date": "2026-01-28",
      "drawdown_to_high_pct": -5.41,
      "is_at_rolling_high": false
    },
    "synthetic_forecast": {
      "estimated_drawdown_pct": -5.16,
      "drawdown_change_today": 0.25
    },
    "risk_metrics": {
      "sharpe_ratio": 1.49,
      "annual_volatility": 22.52,
      "max_drawdown": -12.48,
      "rank_1y": "47",
      "rank_3y": "32",
      "rank_5y": "28"
    }
  }]
}
```

---

### 6. 仅估值

```bash
POST /api/estimate
Content-Type: application/json

{
  "funds": [
    {"code": "110011", "name": "易方达蓝筹", "holding": 10000}
  ]
}
```

**响应示例：**
```json
{
  "results": [{
    "fund_code": "110011",
    "fund_name": "易方达蓝筹精选混合",
    "market": "A股",
    "holding": 10000,
    "benchmark": "沪深300",
    "benchmark_change": 0.35,
    "estimate_change": 0.25,
    "profit": 25.0,
    "top10_ratio": 45.2,
    "position_ratio": 90.0,
    "persistence": 0.55,
    "update_time": "14:30:00"
  }],
  "summary": {
    "total_holding": 10000,
    "total_profit": 25.0,
    "portfolio_change": 0.25
  }
}
```

---

### 7. 仅回撤分析

```bash
POST /api/drawdown
Content-Type: application/json

{
  "funds": [{"code": "110011"}],
  "rolling_days": 90
}
```

**参数：**
- `rolling_days`: 回撤窗口期，支持 30/60/90/120/250 天，默认90

**响应示例：**
```json
{
  "rolling_window": "90日",
  "results": [{
    "fund_code": "110011",
    "current_nav": 5.34,
    "current_date": "2026-02-11",
    "rolling_high": 5.65,
    "high_date": "2026-01-28",
    "drawdown_pct": -5.41,
    "distance_from_high": -0.31,
    "data_points": 90,
    "is_at_high": false
  }],
  "count": 1
}
```

---

### 8. 实时指数涨跌幅

```bash
GET /api/get_indices
```

**响应示例：**
```json
{
  "success": true,
  "indices": [
    {"name": "创业板指", "code": "sz399006", "change": 1.25},
    {"name": "沪深300", "code": "sz399300", "change": 0.35},
    {"name": "中证500", "code": "sh000905", "change": 0.52},
    {"name": "上证指数", "code": "sh000001", "change": 0.28},
    {"name": "纳斯达克100", "code": "usQQQ", "change": -0.15},
    {"name": "恒生指数", "code": "hkHSI", "change": 0.45}
  ],
  "timestamp": "2026-02-12 10:30:00"
}
```

---

### 9. 基金持仓详情

```bash
GET /api/get_fund_detail?code=110011
```

**响应示例：**
```json
{
  "success": true,
  "fund_code": "110011",
  "holdings": [
    {"code": "600519", "name": "贵州茅台", "ratio": 8.52, "change": 1.25, "contribution": 0.107},
    {"code": "000858", "name": "五粮液", "ratio": 7.35, "change": 0.85, "contribution": 0.062}
  ],
  "total_ratio": 45.2,
  "remaining_ratio": 44.8,
  "benchmark": "沪深300",
  "benchmark_change": 0.35,
  "total_change": 0.25,
  "calculation_method": "加权平均: 持仓股票涨跌幅 × 占比 + 剩余部分使用基准指数涨跌幅",
  "timestamp": "14:30:00"
}
```

---

### 10. 单只基金历史净值

```bash
GET /api/get_nav_history?code=110011&days=90
```

**参数：**
- `code` (必填): 基金代码
- `days` (可选): 天数，支持 30/60/90/180/365，默认90

**响应示例：**
```json
{
  "success": true,
  "fund_code": "110011",
  "days": 90,
  "data": {
    "dates": ["2025-11-15", "2025-11-16", "..."],
    "navs": [5.21, 5.23, "..."]
  },
  "statistics": {
    "max_nav": 5.65,
    "max_date": "2026-01-28",
    "min_nav": 5.01,
    "min_date": "2025-12-20",
    "current_nav": 5.34,
    "total_return": 2.50,
    "data_points": 90
  },
  "timestamp": "2026-02-12 10:30:00"
}
```

---

### 11. 批量获取历史净值

```bash
GET /api/get_nav_history_batch?codes=110011,012414,161725&days=180
```

**参数：**
- `codes` (必填): 基金代码，逗号分隔，最多4只
- `days` (可选): 天数，支持 30/90/180/365，默认180

**响应示例：**
```json
{
  "success": true,
  "funds": [
    {
      "code": "110011",
      "data": {"dates": ["..."], "navs": [...]},
      "statistics": {"max_nav": 5.65, "min_nav": 5.01, "current_nav": 5.34, "total_return": 2.50, "data_points": 180}
    }
  ],
  "days": 180,
  "count": 3,
  "timestamp": "2026-02-12 10:30:00"
}
```

---

## 🤖 支持的 AI 提供商

| 提供商 | AI_PROVIDER 值 |
|--------|----------------|
| DeepSeek | `deepseek` |
| OpenAI | `openai` |
| Azure OpenAI | `azure_openai` |
| Claude | `anthropic` |
| Gemini | `gemini` |
| Ollama | `ollama` |
| 自定义兼容 API | `openai_compatible` |

---

## ☁️ 部署

### Railway / Render

1. Fork 本项目
2. 连接 GitHub 仓库
3. 设置环境变量 `AI_PROVIDER` 和 `AI_API_KEY`
4. 自动部署完成

### 前端部署

纯静态 HTML，可部署至 GitHub Pages / Vercel / Netlify

修改 `index.html` 中的 `API_BASE_URL` 指向后端地址

---

## ⚠️ 免责声明

- 本项目仅供学习交流，不构成任何投资建议
- 基金数据来源于 akshare，仅供参考
- 投资有风险，入市需谨慎

---

## License

MIT
