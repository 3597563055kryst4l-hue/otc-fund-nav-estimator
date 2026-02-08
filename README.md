# 基金数据查询系统

基于 Flask 的基金/股票数据查询后端服务，接入 DeepSeek AI 提供智能分析。

## 功能特性

- 📈 基金/股票数据查询（基于 akshare）
- 🤖 多 AI 提供商支持（DeepSeek / OpenAI / Claude / Gemini / Ollama / 自定义）
- 🌐 RESTful API 接口
- ⚡ 速率限制保护
- 🔒 CORS 跨域支持
- 🔧 灵活的环境变量配置

## 技术栈

- **后端**: Flask + Flask-CORS + Flask-Limiter
- **数据**: akshare + pandas
- **AI**: 支持 DeepSeek / OpenAI / Azure OpenAI / Claude / Gemini / Ollama / 自定义 OpenAI 兼容 API
- **部署**: 支持 Railway/Render/PythonAnywhere 等

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

#### 通用配置方式（推荐）

```env
AI_PROVIDER=deepseek
AI_API_KEY=your_api_key_here
FLASK_ENV=production
FLASK_DEBUG=0
```

#### 支持的 AI 提供商

| 提供商 | AI_PROVIDER | 说明 |
|--------|-------------|------|
| DeepSeek | `deepseek` | 默认，国产大模型 |
| OpenAI | `openai` | GPT-3.5/GPT-4 |
| Azure OpenAI | `azure_openai` | 微软 Azure 服务 |
| Claude | `anthropic` | Anthropic Claude 3 |
| Gemini | `gemini` | Google Gemini |
| Ollama | `ollama` | 本地运行开源模型 |
| 自定义 | `openai_compatible` | 其他兼容 OpenAI 格式的 API |

#### 配置示例

**使用 OpenAI：**
```env
AI_PROVIDER=openai
AI_API_KEY=sk-xxxxxxxx
AI_MODEL=gpt-3.5-turbo
```

**使用 Claude：**
```env
AI_PROVIDER=anthropic
AI_API_KEY=sk-ant-xxxxx
AI_MODEL=claude-3-sonnet-20240229
```

**使用本地 Ollama：**
```env
AI_PROVIDER=ollama
AI_API_URL=http://localhost:11434/api/generate
AI_MODEL=llama2
```

**使用 SillyTavern/其他兼容 API：**
```env
AI_PROVIDER=openai_compatible
AI_API_KEY=your_key
AI_API_URL=https://api.example.com/v1/chat/completions
AI_MODEL=model-name
```

> 💡 **向后兼容**：如果设置了旧的 `DEEPSEEK_API_KEY`，系统会自动识别并使用 DeepSeek

### 4. 运行

```bash
python test.py
```

服务将在 `http://localhost:5000` 启动

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/xxx` | POST/GET | 基金数据查询接口 |

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
   - Start Command: `python test.py`
5. 添加环境变量

## ⚠️ 注意事项

- **不要将 `.env` 文件上传到 GitHub**，已添加到 `.gitignore`
- 生产环境请修改 CORS 配置，限制为特定域名
- 建议添加 API 认证机制

## License

MIT
