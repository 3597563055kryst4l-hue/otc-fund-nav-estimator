# FundVision - 基金估值与回撤分析系统

基于 Flask 的基金估值与回撤分析系统，支持 AI 智能解析和手动搜索添加，提供实时估值和 90 日高点回撤分析。

## 功能特性

- 📊 **基金估值分析** - 实时估算基金当日涨跌幅
- 📉 **90日高点回撤** - 分析基金距离近期高点的回撤幅度
- 🤖 **AI 智能解析** - 支持自然语言输入，自动识别基金代码和持仓
- 🔍 **基金搜索** - 支持代码/名称/拼音模糊搜索
- 📝 **混合输入** - AI 解析和手动搜索可同时使用，统一列表管理
- 💾 **本地缓存** - 自动保存基金列表到浏览器本地存储
- 🌐 **RESTful API** - 提供完整的 API 接口
- ⚡ **多 AI 提供商支持** - DeepSeek / OpenAI / Claude / Gemini / Ollama / 自定义

## 技术栈

- **后端**: Flask + Flask-CORS + Flask-Limiter
- **前端**: 原生 HTML + Tailwind CSS + GSAP 动画
- **数据**: akshare + pandas
- **AI**: 支持多提供商（DeepSeek / OpenAI / Azure OpenAI / Claude / Gemini / Ollama）

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/你的用户名/fund.git
cd fund
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

复制 `.env.example` 为 `.env`，并填写你的 API Key：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
AI_PROVIDER=deepseek
AI_API_KEY=your_api_key_here
FLASK_ENV=production
FLASK_DEBUG=0
```

> 💡 **向后兼容**：如果设置了旧的 `DEEPSEEK_API_KEY`，系统会自动识别并使用 DeepSeek

### 4. 运行服务

```bash
python app.py
```

服务启动后：
- 后端 API: `http://localhost:5000`
- 前端界面: 直接打开 `index.html` 或使用 Live Server

## 使用说明

### 前端界面

1. **AI 智能解析**（可选）
   - 点击 "AI 智能解析" 展开输入区域
   - 粘贴持仓数据（支持任意自然语言格式）
   - 点击 "智能解析并添加"

2. **搜索添加**
   - 输入基金代码或名称进行搜索
   - 从下拉列表选择基金
   - 输入持仓金额（可选，默认为0）
   - 点击 "添加"

3. **执行分析**
   - 添加完所有基金后，点击 "执行分析"
   - 查看估值与回撤明细

### 支持的输入格式示例

```
易方达蓝筹精选混合 110011 10000元
我买了20000块的白酒基金，代码是012414
012414,15000
白酒基金
110011
```

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `GET /api/health` | - | 健康检查 |
| `GET /api/search_fund?keyword=xxx` | - | 基金搜索 |
| `GET /api/fund_info/<code>` | - | 获取基金基本信息 |
| `POST /api/parse_funds` | JSON | AI 解析自然语言 |
| `POST /api/fund_analysis` | JSON | 基金分析（估值+回撤） |
| `POST /api/estimate` | JSON | 仅估值 |
| `POST /api/drawdown` | JSON | 仅回撤 |

### API 请求示例

**基金分析：**
```bash
curl -X POST http://localhost:5000/api/fund_analysis \
  -H "Content-Type: application/json" \
  -d '{
    "funds": [
      {"code": "110011", "name": "易方达蓝筹", "holding": 10000},
      {"code": "012414", "name": "白酒基金", "holding": 20000}
    ]
  }'
```

**AI 解析：**
```bash
curl -X POST http://localhost:5000/api/parse_funds \
  -H "Content-Type: application/json" \
  -d '{"text": "我买了10000元的易方达蓝筹110011"}'
```

## 支持的 AI 提供商

| 提供商 | AI_PROVIDER | 说明 |
|--------|-------------|------|
| DeepSeek | `deepseek` | 默认，国产大模型 |
| OpenAI | `openai` | GPT-3.5/GPT-4 |
| Azure OpenAI | `azure_openai` | 微软 Azure 服务 |
| Claude | `anthropic` | Anthropic Claude 3 |
| Gemini | `gemini` | Google Gemini |
| Ollama | `ollama` | 本地运行开源模型 |
| 自定义 | `openai_compatible` | 其他兼容 OpenAI 格式的 API |

## 部署指南

### 部署到 Railway（推荐）

1. Fork 本项目到你的 GitHub
2. 登录 [Railway](https://railway.app)
3. 新建项目 -> Deploy from GitHub repo
4. 添加环境变量（在 Railway Dashboard 的 Variables 中设置）
5. 自动部署完成

### 部署到 Render

1. Fork 本项目
2. 登录 [Render](https://render.com)
3. New Web Service -> Connect GitHub repo
4. 设置：
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python app.py`
5. 添加环境变量

### 前端部署

前端为纯静态 HTML，可以部署到：
- GitHub Pages
- Vercel / Netlify
- 任何静态文件服务器

修改 `index.html` 中的 `API_BASE_URL` 指向你的后端服务地址。

## ⚠️ 注意事项

- **不要将 `.env` 文件上传到 GitHub**，已添加到 `.gitignore`
- 生产环境请修改 CORS 配置，限制为特定域名
- AI 解析功能需要配置有效的 API Key
- 基金数据来源于 akshare，仅供参考

## License

MIT
