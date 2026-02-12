from flask import Flask, request, jsonify, abort
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import akshare as ak
import pandas as pd
import requests
import re
import time
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from functools import wraps
import numpy as np
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 安全配置
app.config['JSON_AS_ASCII'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 限制请求体16MB

# CORS配置（生产环境请限制为特定域名）
CORS(app, resources={
    r"/api/*": {
        "origins": "*",  # 必须是 *，不能是数组
        "methods": ["POST", "GET", "OPTIONS"],
        "allow_headers": ["Content-Type"],
        "supports_credentials": True
    }
})

# 速率限制配置
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# ==========================================
# 通用AI服务配置 - 支持多提供商（仅用于解析基金）
# ==========================================

class AIProvider:
    """AI提供商配置"""
    
    # 支持的提供商配置模板
    PROVIDERS = {
        'deepseek': {
            'api_url': 'https://api.deepseek.com/v1/chat/completions',
            'model': 'deepseek-chat',
            'auth_header': 'Authorization',
            'auth_prefix': 'Bearer ',
            'request_format': 'openai',  # 请求格式
            'response_path': 'choices.0.message.content',  # 响应提取路径
        },
        'openai': {
            'api_url': 'https://api.openai.com/v1/chat/completions',
            'model': 'gpt-3.5-turbo',
            'auth_header': 'Authorization',
            'auth_prefix': 'Bearer ',
            'request_format': 'openai',
            'response_path': 'choices.0.message.content',
        },
        'azure_openai': {
            'api_url': '',  # 需要填写 Azure Endpoint
            'model': 'gpt-35-turbo',
            'auth_header': 'api-key',
            'auth_prefix': '',
            'request_format': 'openai',
            'response_path': 'choices.0.message.content',
        },
        'anthropic': {
            'api_url': 'https://api.anthropic.com/v1/messages',
            'model': 'claude-3-sonnet-20240229',
            'auth_header': 'x-api-key',
            'auth_prefix': '',
            'request_format': 'anthropic',
            'response_path': 'content.0.text',
        },
        'gemini': {
            'api_url': 'https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent',
            'model': 'gemini-pro',
            'auth_header': 'key',  # Gemini使用URL参数或header
            'auth_prefix': '',
            'request_format': 'gemini',
            'response_path': 'candidates.0.content.parts.0.text',
        },
        'ollama': {
            'api_url': 'http://localhost:11434/api/generate',
            'model': 'llama2',
            'auth_header': '',
            'auth_prefix': '',
            'request_format': 'ollama',
            'response_path': 'response',
        },
        'openai_compatible': {
            'api_url': '',  # 自定义兼容OpenAI的API地址
            'model': '',    # 自定义模型名
            'auth_header': 'Authorization',
            'auth_prefix': 'Bearer ',
            'request_format': 'openai',
            'response_path': 'choices.0.message.content',
        }
    }
    
    def __init__(self):
        # 读取环境变量配置
        self.provider = os.environ.get('AI_PROVIDER', 'deepseek').lower()
        self.api_key = os.environ.get('AI_API_KEY') or os.environ.get(f'{self.provider.upper()}_API_KEY')
        self.api_url = os.environ.get('AI_API_URL') or os.environ.get(f'{self.provider.upper()}_API_URL')
        self.model = os.environ.get('AI_MODEL')
        
        # 获取提供商配置
        self.config = self.PROVIDERS.get(self.provider, self.PROVIDERS['openai_compatible']).copy()
        
        # 如果环境变量有设置，覆盖默认值
        if self.api_url:
            self.config['api_url'] = self.api_url
        if self.model:
            self.config['model'] = self.model
            
        # 向后兼容：如果设置了旧的DEEPSEEK配置，自动使用
        if not self.api_key:
            deepseek_key = os.environ.get('DEEPSEEK_API_KEY')
            if deepseek_key:
                self.provider = 'deepseek'
                self.api_key = deepseek_key
                self.config = self.PROVIDERS['deepseek'].copy()
                deepseek_url = os.environ.get('DEEPSEEK_API_URL')
                if deepseek_url:
                    self.config['api_url'] = deepseek_url
    
    def is_configured(self) -> bool:
        """检查是否已配置"""
        return bool(self.api_key and self.config.get('api_url'))
    
    def get_headers(self) -> dict:
        """获取请求头"""
        headers = {'Content-Type': 'application/json'}
        auth_header = self.config.get('auth_header')
        if auth_header and self.api_key:
            auth_prefix = self.config.get('auth_prefix', '')
            headers[auth_header] = f'{auth_prefix}{self.api_key}'
        return headers
    
    def build_request_body(self, prompt: str, temperature: float = 0.7, max_tokens: int = 2000) -> dict:
        """构建请求体"""
        fmt = self.config.get('request_format', 'openai')
        model = self.config.get('model', 'gpt-3.5-turbo')
        
        if fmt == 'openai':
            return {
                'model': model,
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': temperature,
                'max_tokens': max_tokens
            }
        elif fmt == 'anthropic':
            return {
                'model': model,
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': max_tokens,
                'temperature': temperature
            }
        elif fmt == 'gemini':
            return {
                'contents': [{
                    'parts': [{'text': prompt}]
                }],
                'generationConfig': {
                    'temperature': temperature,
                    'maxOutputTokens': max_tokens
                }
            }
        elif fmt == 'ollama':
            return {
                'model': model,
                'prompt': prompt,
                'stream': False,
                'options': {
                    'temperature': temperature
                }
            }
        else:
            # 默认使用 OpenAI 格式
            return {
                'model': model,
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': temperature,
                'max_tokens': max_tokens
            }
    
    def extract_response(self, data: dict) -> str:
        """从响应中提取内容"""
        path = self.config.get('response_path', 'choices.0.message.content')
        keys = path.split('.')
        
        try:
            value = data
            for key in keys:
                if key.isdigit():
                    value = value[int(key)]
                else:
                    value = value[key]
            return str(value) if value else ""
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"无法从响应中提取内容: {e}, path={path}, data={json.dumps(data)[:500]}")
            return ""
    
    def chat(self, prompt: str, temperature: float = 0.7, max_tokens: int = 2000, timeout: int = 60) -> str:
        """发送聊天请求"""
        if not self.is_configured():
            raise ValueError(f"AI提供商 '{self.provider}' 未配置")
        
        url = self.config.get('api_url')
        headers = self.get_headers()
        body = self.build_request_body(prompt, temperature, max_tokens)
        
        # Gemini 特殊处理：API key 在 URL 参数中
        if self.provider == 'gemini' and self.api_key:
            url = f"{url}?key={self.api_key}"
        
        try:
            response = requests.post(
                url,
                headers=headers,
                json=body,
                timeout=timeout
            )
            
            if response.status_code != 200:
                logger.error(f"AI API错误: {response.status_code} - {response.text[:500]}")
                raise Exception(f"AI服务返回错误: {response.status_code}")
            
            data = response.json()
            content = self.extract_response(data)
            
            if not content:
                raise ValueError("AI返回内容为空")
            
            return content
            
        except requests.exceptions.Timeout:
            logger.error("AI请求超时")
            raise Exception("AI服务请求超时")
        except requests.exceptions.ConnectionError:
            logger.error("无法连接到AI服务")
            raise Exception("无法连接到AI服务，请检查网络或API地址")
        except Exception as e:
            logger.error(f"AI请求异常: {e}")
            raise

    def get_info(self) -> dict:
        """获取当前配置信息（不含敏感信息）"""
        return {
            'provider': self.provider,
            'model': self.config.get('model', 'unknown'),
            'configured': self.is_configured(),
            'api_url': self.config.get('api_url', '')[:30] + '...' if self.config.get('api_url') else ''
        }

# 初始化AI提供商
ai_provider = AIProvider()

# 向后兼容的变量
DEEPSEEK_API_KEY = ai_provider.api_key if ai_provider.provider == 'deepseek' else None
DEEPSEEK_API_URL = ai_provider.config.get('api_url') if ai_provider.provider == 'deepseek' else None

if not ai_provider.is_configured():
    logger.warning("⚠️  AI服务未配置，请在.env中设置 AI_API_KEY 和 AI_PROVIDER")
    logger.info("💡 支持的AI提供商: deepseek, openai, azure_openai, anthropic, gemini, ollama, openai_compatible")
else:
    info = ai_provider.get_info()
    logger.info(f"✅ AI服务已配置: {info['provider']} / {info['model']}")

# ==========================================
# 安全中间件和辅助函数
# ==========================================

def sanitize_fund_code(code: str) -> Optional[str]:
    """清洗基金代码，确保是6位数字"""
    if not code:
        return None
    code = str(code).strip()
    # 移除所有非数字字符
    code = re.sub(r'\D', '', code)
    # 验证是否为6位
    if re.match(r'^\d{6}$', code):
        return code
    return None

def sanitize_input(text: str, max_length: int = 5000) -> str:
    """清洗用户输入，防止Prompt Injection"""
    if not text:
        return ""
    # 长度限制
    text = text[:max_length]
    # 移除潜在的危险字符（保留中文、英文、数字、常见标点）
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s\.,;:!?\-_(){}\[\]\'"￥，。；：！？（）【】]', '', text)
    return text.strip()

def validate_funds_data(funds: list) -> Tuple[bool, str]:
    """验证基金数据格式"""
    if not isinstance(funds, list) or len(funds) == 0:
        return False, "基金列表不能为空"
    if len(funds) > 20:  # 限制最多20只基金，防止滥用
        return False, "单次最多分析20只基金"
    
    for fund in funds:
        if not isinstance(fund, dict):
            return False, "基金数据格式错误"
        # 支持通过代码或名称中的任意一个来识别基金
        code = sanitize_fund_code(fund.get('code', ''))
        name = fund.get('name', '').strip()
        
        if not code and not name:
            return False, f"基金代码和名称不能同时为空: {fund}"
        
        # 如果有持仓金额，验证其格式
        holding = fund.get('holding', 0)
        if holding is not None and holding != '':
            try:
                holding_val = float(holding)
                if holding_val < 0 or holding_val > 100000000:  # 限制合理范围
                    return False, "持仓金额超出合理范围"
            except:
                return False, "持仓金额格式错误"
    return True, ""

# ==========================================
# 系统一：净值回撤分析模块（默认90日高点）
# ==========================================

def get_fund_drawdown(fund_code="016665", rolling_days=90, target_date=None):
    """
    获取基金净值及距离近期高点的回撤幅度
    返回的drawdown_pct为正数表示下跌幅度（如10.98表示下跌10.98%）
    在分析器中会被转换为负数用于显示
    """
    try:
        df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
    except Exception as e:
        logger.error(f"获取数据失败 {fund_code}: {e}")
        return None
    
    if df is None or df.empty:
        logger.warning(f"无法获取基金 {fund_code} 数据")
        return None
    
    df = df.iloc[:, :2].copy()
    df.columns = ['date', 'nav']
    df['date'] = pd.to_datetime(df['date'])
    df['nav'] = pd.to_numeric(df['nav'], errors='coerce')
    df = df.dropna().sort_values('date')
    
    if target_date:
        target_dt = pd.to_datetime(target_date)
        target_row = df[df['date'] == target_dt]
        if target_row.empty:
            logger.info(f"未找到 {target_date} 的数据，将使用最新可用数据")
            target_row = df.iloc[-1]
        else:
            target_row = target_row.iloc[0]
    else:
        target_row = df.iloc[-1]
    
    current_nav = float(target_row['nav'])
    current_date = target_row['date']
    
    hist_df = df[df['date'] <= current_date].tail(rolling_days * 2)
    if len(hist_df) < rolling_days:
        logger.warning(f"近{rolling_days}个交易日数据不足，实际只有{len(hist_df)}天")
        recent_df = hist_df
    else:
        recent_df = hist_df.tail(rolling_days)
    
    if recent_df.empty:
        logger.warning(f"近{rolling_days}日无数据")
        return None
    
    rolling_high = float(recent_df['nav'].max())
    high_date = recent_df[recent_df['nav'] == rolling_high]['date'].iloc[-1]
    
    # 计算回撤（正数表示下跌百分比）
    drawdown_pct = float((rolling_high - current_nav) / rolling_high * 100)
    
    result = {
        'fund_code': str(fund_code),
        'current_nav': float(round(current_nav, 4)),
        'current_date': str(current_date.strftime('%Y-%m-%d')),
        'rolling_high': float(round(rolling_high, 4)),
        'high_date': str(high_date.strftime('%Y-%m-%d')),
        'drawdown_pct': float(round(drawdown_pct, 2)),  # 正数表示下跌
        'distance_from_high': float(round(rolling_high - current_nav, 4)),
        'data_points': int(len(recent_df)),
        'is_at_high': bool(abs(drawdown_pct) < 0.01)
    }
    
    return result

# ==========================================
# 系统二：盘中估值引擎
# ==========================================

class SmartFundEstimator:
    def __init__(self):
        self.index_codes = {
            '创业板指': 'sz399006',
            '沪深300': 'sz399300',
            '中证500': 'sh000905',
            '上证指数': 'sh000001',
            '深证成指': 'sz399001',
            '纳斯达克100': 'usQQQ',
            '恒生指数': 'hkHSI',
            '恒生科技': 'hkHSTECH',
            '中证新能': 'sz399808',
            '中证科技': 'sh000931',
        }
        
        self.etf_map = {
            '云计算': ('516510', '易方达中证云计算ETF'),
            '大数据': ('515400', '富国中证大数据ETF'),
            '人工智能': ('515980', '华富中证人工智能ETF'),
            'AI': ('515980', '华富中证人工智能ETF'),
            '芯片': ('512760', '国泰CES半导体ETF'),
            '半导体': ('512480', '国联安中证半导体ETF'),
            '新能源': ('516160', '南方中证新能源ETF'),
            '光伏': ('515790', '华泰柏瑞中证光伏ETF'),
            '碳中和': ('159790', '易方达中证碳中和ETF'),
            '医疗': ('512170', '华宝中证医疗ETF'),
            '医药': ('512010', '易方达沪深300医药ETF'),
            '白酒': ('512690', '鹏华中证酒ETF'),
            '酒': ('512690', '鹏华中证酒ETF'),
            '军工': ('512660', '国泰中证军工ETF'),
            '券商': ('512000', '华宝中证全指证券ETF'),
            '证券': ('512000', '华宝中证全指证券ETF'),
            '银行': ('512800', '华宝中证银行ETF'),
            '地产': ('512200', '南方中证全指房地产ETF'),
            '房地产': ('512200', '南方中证全指房地产ETF'),
            '传媒': ('512980', '广发中证传媒ETF'),
            '游戏': ('159869', '华夏中证动漫游戏ETF'),
            '动漫游戏': ('159869', '华夏中证动漫游戏ETF'),
            '科技': ('515000', '华宝中证科技龙头ETF'),
            '5G': ('515050', '华夏中证5G通信主题ETF'),
            '通信': ('515050', '华夏中证5G通信主题ETF'),
            '创新药': ('159992', '银华中证创新药产业ETF'),
            '消费电子': ('159732', '华夏国证消费电子主题ETF'),
            '机器人': ('562500', '华夏中证机器人ETF'),
            '机床': ('159663', '华夏中证机床ETF'),
            '工业母机': ('159663', '华夏中证机床ETF'),
            '稀有金属': ('159608', '嘉实中证稀有金属主题ETF'),
            '稀土': ('516780', '华泰柏瑞中证稀土产业ETF'),
            '有色': ('512400', '南方中证申万有色金属ETF'),
            '有色金属': ('512400', '南方中证申万有色金属ETF'),
            '化工': ('516020', '华宝中证细分化工产业ETF'),
            '建材': ('159745', '国泰中证全指建筑材料ETF'),
            '钢铁': ('515210', '国泰中证钢铁ETF'),
            '煤炭': ('515220', '国泰中证煤炭ETF'),
            '石油': ('501096', '易方达中证石化产业ETF'),
            '农业': ('159825', '富国中证农业ETF'),
            '畜牧': ('159867', '鹏华中证畜牧养殖ETF'),
            '养殖': ('159867', '鹏华中证畜牧养殖ETF'),
            '旅游': ('159766', '旅游ETF'),
            '教育': ('513360', '教育ETF'),
            '金融科技': ('516100', '金融科技ETF'),
            '智能制造': ('516800', '智能制造ETF'),
            '高端制造': ('516320', '高端制造ETF'),
            '智能汽车': ('159889', '智能汽车ETF'),
            '新能源汽车': ('516390', '新能源汽车ETF'),
            '新能源车': ('515030', '新能源车ETF'),
            '电池': ('159755', '电池ETF'),
            '储能': ('159866', '储能ETF'),
            '电力': ('159611', '电力ETF'),
            '绿色电力': ('159669', '绿色电力ETF'),
            '央企': ('512950', '央企ETF'),
            '国企': ('512810', '国企ETF'),
            '红利': ('510880', '红利ETF'),
            '低波动': ('512260', '低波动ETF'),
            '价值': ('510030', '价值ETF'),
            '成长': ('510760', '成长ETF'),
            '创业板': ('159915', '创业板ETF'),
            '科创板': ('588000', '科创50ETF'),
            '科创50': ('588000', '科创50ETF'),
            '双创': ('159780', '双创ETF'),
            '沪深300': ('510300', '沪深300ETF'),
            '中证500': ('510500', '中证500ETF'),
            '中证1000': ('512100', '中证1000ETF'),
            '上证50': ('510050', '上证50ETF'),
            '深证100': ('159901', '深证100ETF'),
            '创业板50': ('159949', '创业板50ETF'),
            'MSCI': ('512520', 'MSCI ETF'),
            'A50': ('159601', 'A50ETF'),
            '沪港深': ('517010', '易方达中证沪港深500ETF'),
        }
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        logger.info("★ 基金估值系统 v6.0 [精简版 - 仅估值与回撤]")

    def is_link_fund(self, fund_name: str) -> bool:
        return bool(re.search(r'联接|link', fund_name, re.IGNORECASE))

    def is_etf_code(self, code: str, name: str) -> bool:
        code = str(code).strip()
        if re.match(r'^(510|511|512|515|516|517|518|560|561|562|563|564|565|566|567|568|569|159)\d{3}$', code):
            return True
        if 'ETF' in name or 'etf' in name:
            return True
        return False

    def find_etf_by_fund_name(self, fund_name: str) -> Tuple[Optional[str], Optional[str]]:
        clean = re.sub(r'联接[ABC]?|Link|[A-C]$', '', fund_name, flags=re.IGNORECASE).strip()
        
        for keyword, (code, name) in self.etf_map.items():
            if keyword in clean:
                return code, name
        
        companies = ['易方达', '华夏', '南方', '国泰', '华宝', '广发', '富国', '嘉实', 
                     '华泰柏瑞', '鹏华', '银华', '国联安', '华富', '汇添富', '工银', '博时']
        for comp in companies:
            if clean.startswith(comp):
                keyword = clean[len(comp):].strip()
                for kw, (code, name) in self.etf_map.items():
                    if kw in keyword:
                        return code, name
                break
        
        return None, None

    def detect_market_and_benchmark(self, holdings_df, fund_name: str) -> Tuple[str, str, float]:
        us_count = 0
        hk_count = 0
        a_sh_count = 0
        a_sz_count = 0
        
        for _, row in holdings_df.iterrows():
            code = str(row['股票代码']).strip()
            
            if re.match(r'^[A-Z]{1,5}(\.[A-Z])?$', code):
                us_count += 1
            elif re.match(r'^\d{5}$', code):
                hk_count += 1
            elif len(code) == 6 and code.isdigit():
                if code.startswith('6'):
                    a_sh_count += 1
                else:
                    a_sz_count += 1
        
        total = us_count + hk_count + a_sh_count + a_sz_count
        
        if us_count >= 3 or (total > 0 and us_count / total > 0.5):
            market = '美股'
            benchmark = '纳斯达克100'
            position = 0.90
        elif hk_count >= 3 or (total > 0 and hk_count / total > 0.5):
            market = '港股'
            if '科技' in fund_name:
                benchmark = '恒生科技'
            else:
                benchmark = '恒生指数'
            position = 0.88
        else:
            market = 'A股'
            gem_count = sum(1 for _, row in holdings_df.iterrows() 
                          if str(row['股票代码']).startswith('300'))
            if gem_count >= 4:
                benchmark = '创业板指'
            elif a_sh_count > a_sz_count:
                benchmark = '沪深300'
            else:
                benchmark = '创业板指' if gem_count >= 2 else '沪深300'
            position = 0.90 if (gem_count >= 4) else 0.88
        
        return market, benchmark, position

    def get_stock_changes(self, codes: List[str], names: List[str]) -> Dict[str, float]:
        results = {}
        if not codes:
            return results
            
        tencent_codes = []
        mapping = {}
        
        for code, name in zip(codes, names):
            code = str(code).strip()
            
            if len(code) == 6 and code.isdigit():
                if code.startswith(('5', '1')):
                    prefix = 'sh' if code.startswith('5') else 'sz'
                    tcode = f"{prefix}{code}"
                elif code.startswith('6'):
                    tcode = f"sh{code}"
                else:
                    tcode = f"sz{code}"
            elif len(code) == 5 and code.isdigit():
                tcode = f"hk{code}"
            else:
                tcode = f"us{code.replace('.', '_')}"
            
            tencent_codes.append(tcode)
            mapping[tcode] = code
        
        for i in range(0, len(tencent_codes), 60):
            batch = tencent_codes[i:i+60]
            try:
                url = f"http://qt.gtimg.cn/q={','.join(batch)}"
                resp = requests.get(url, headers=self.headers, timeout=15)
                resp.encoding = 'gbk'
                
                for line in resp.text.split(';'):
                    if '=' not in line:
                        continue
                    parts = line.split('=')
                    if len(parts) < 2:
                        continue
                    
                    match = re.search(r'(us[A-Z_]+|sh\d{6}|sz\d{6}|hk\d{5})', parts[0])
                    if not match:
                        continue
                    
                    tcode = match.group(0)
                    orig_code = mapping.get(tcode)
                    if not orig_code:
                        continue
                    
                    fields = parts[1].strip('"').split('~')
                    if len(fields) > 32:
                        try:
                            change = float(fields[32]) if fields[32] else 0.0
                            if change == 0 and len(fields) > 4:
                                curr = float(fields[3]) if fields[3] else 0
                                prev = float(fields[4]) if fields[4] else 0
                                if prev > 0:
                                    change = (curr - prev) / prev * 100
                            results[orig_code] = change
                        except:
                            results[orig_code] = 0.0
            except Exception as e:
                logger.error(f"行情接口错误: {e}")
            
            time.sleep(0.2)
        
        return results

    def get_index_change(self, index_name: str) -> float:
        code = self.index_codes.get(index_name, 'sz399006')
        try:
            url = f"http://qt.gtimg.cn/q={code}"
            resp = requests.get(url, headers=self.headers, timeout=10)
            resp.encoding = 'gbk'
            if '=' in resp.text:
                fields = resp.text.split('=')[1].strip('"').split('~')
                if len(fields) > 32:
                    return float(fields[32]) if fields[32] else 0.0
        except:
            pass
        return 0.0

    def estimate_link_fund(self, fund_code: str, fund_name: str, holding: float) -> Optional[Dict]:
        logger.info(f"\n【{fund_name}】{fund_code} [联接基金模式]")
        
        try:
            df = ak.fund_portfolio_hold_em(symbol=fund_code, date="2025")
            if df.empty:
                df = ak.fund_portfolio_hold_em(symbol=fund_code, date="2024")
            
            etf_code = None
            etf_name = None
            etf_ratio = 95.0
            
            if not df.empty:
                latest_q = sorted(df['季度'].unique(), reverse=True)[0]
                data = df[df['季度'] == latest_q]
                
                if len(data) > 0:
                    top1 = data.iloc[0]
                    top1_ratio = float(top1['占净值比例'])
                    top1_name = str(top1['股票名称'])
                    top1_code = str(top1['股票代码'])
                    
                    if top1_ratio > 80 and self.is_etf_code(top1_code, top1_name):
                        etf_code = top1_code
                        etf_name = top1_name
                        etf_ratio = top1_ratio
                        logger.info(f"  目标ETF: {etf_name}({etf_code}) 占比{etf_ratio:.1f}%")
                    else:
                        logger.warning(f"  警告：持仓占比过低({top1_ratio}%)，akshare返回了成分股")
                        logger.info(f"  尝试通过基金名称反向查找ETF...")
            
            if not etf_code:
                etf_code, etf_name = self.find_etf_by_fund_name(fund_name)
                if etf_code:
                    logger.info(f"  反向查找ETF: {etf_name}({etf_code}) 预估占比{etf_ratio:.1f}%")
                else:
                    logger.warning(f"  未能找到对应ETF，回退到普通模式")
                    return self.estimate_normal_fund(fund_code, fund_name, holding, df)
            
            etf_changes = self.get_stock_changes([etf_code], [etf_name])
            etf_change = etf_changes.get(etf_code, 0)
            
            if etf_change == 0:
                logger.warning(f"  未能获取ETF行情")
                return None
            
            position = min(etf_ratio * 1.02, 98) / 100
            link_change = etf_change * position
            profit = holding * link_change / 100
            
            logger.info(f"  ETF行情: {etf_change:+.2f}% | 仓位系数: {position*100:.0f}%")
            logger.info(f"  结果: {link_change:+.2f}% | 盈亏: {profit:+,.0f}元")
            
            return {
                'fund_code': str(fund_code),
                'fund_name': str(fund_name),
                'market': 'A股-联接',
                'holding': float(holding),
                'benchmark': str(etf_name),
                'benchmark_change': float(round(etf_change, 2)),
                'estimate_change': float(round(link_change, 2)),
                'profit': float(round(profit, 2)),
                'top10_ratio': float(round(etf_ratio, 1)),
                'position_ratio': float(round(position * 100, 0)),
                'persistence': 1.0,
                'note': f'跟踪{etf_code}',
                'update_time': datetime.now().strftime('%H:%M:%S')
            }
            
        except Exception as e:
            logger.error(f"  联接基金处理失败: {e}")
            return self.estimate_normal_fund(fund_code, fund_name, holding)

    def estimate_normal_fund(self, fund_code: str, fund_name: str, holding: float, df=None) -> Optional[Dict]:
        try:
            if df is None:
                df = ak.fund_portfolio_hold_em(symbol=fund_code, date="2025")
                if df.empty:
                    df = ak.fund_portfolio_hold_em(symbol=fund_code, date="2024")
                if df.empty:
                    return None
            
            latest_q = sorted(df['季度'].unique(), reverse=True)[0]
            data = df[df['季度'] == latest_q].head(10)
            
            stocks = []
            for _, row in data.iterrows():
                stocks.append({
                    'code': str(row['股票代码']),
                    'name': str(row['股票名称']),
                    'ratio': float(row['占净值比例'])
                })
            
            if not stocks:
                return None
            
            market, benchmark, est_position = self.detect_market_and_benchmark(data, fund_name)
            logger.info(f"  检测市场: {market} | 基准: {benchmark} | 估算仓位: {est_position*100:.0f}%")
            
            codes = [s['code'] for s in stocks]
            names = [s['name'] for s in stocks]
            changes = self.get_stock_changes(codes, names)
            
            top10_contrib = 0
            valid_count = 0
            for s in stocks:
                chg = changes.get(s['code'], 0)
                if chg != 0:
                    top10_contrib += chg * s['ratio'] / 100
                    valid_count += 1
                    logger.info(f"  {s['code']}({s['name']}): {chg:+.2f}% × {s['ratio']}% = {chg * s['ratio'] / 100:+.3f}%")
            
            if valid_count == 0:
                return None
            
            top10_ratio = sum(s['ratio'] for s in stocks)
            bench_chg = self.get_index_change(benchmark)
            logger.info(f"  基准{benchmark}: {bench_chg:+.2f}%")
            
            remaining_ratio = max(0, est_position * 100 - top10_ratio)
            remaining_contrib = bench_chg * (remaining_ratio / 100)
            
            total_change = top10_contrib + remaining_contrib
            
            if market == '美股':
                total_change *= 1.10
            elif market == '港股':
                if '科技' in fund_name:
                    total_change *= 1.20
                else:
                    total_change *= 1.15
            elif '科技' in fund_name or '科融' in fund_name:
                total_change *= 1.20
            elif '碳中和' in fund_name or '新能源' in fund_name:
                total_change *= 1.30
            
            profit = holding * total_change / 100
            
            logger.info(f"  前十占比: {top10_ratio:.1f}% | 剩余补齐: {remaining_ratio:.1f}%")
            logger.info(f"  结果: {total_change:+.2f}% | 盈亏: {profit:+,.0f}元")
            
            return {
                'fund_code': str(fund_code),
                'fund_name': str(fund_name),
                'market': str(market),
                'holding': float(holding),
                'benchmark': str(benchmark),
                'benchmark_change': float(round(bench_chg, 2)),
                'estimate_change': float(round(total_change, 2)),
                'profit': float(round(profit, 2)),
                'top10_ratio': float(round(top10_ratio, 1)),
                'position_ratio': float(round(est_position * 100, 0)),
                'persistence': 0.75 if market == '美股' else (0.65 if market == '港股' else 0.55),
                'update_time': datetime.now().strftime('%H:%M:%S')
            }
            
        except Exception as e:
            logger.error(f"  普通基金估算失败: {e}")
            return None

    def estimate_fund(self, fund_code: str, fund_name: str, holding: float) -> Optional[Dict]:
        if self.is_link_fund(fund_name):
            return self.estimate_link_fund(fund_code, fund_name, holding)
        else:
            return self.estimate_normal_fund(fund_code, fund_name, holding)


# ==========================================
# 整合层：估值与回撤分析器（精简版）
# ==========================================

class FundAnalyzer:
    """
    基金分析器 - 精简版
    仅提供实时估值和滚动回撤数据，不包含投资建议
    """
    
    def __init__(self):
        self.estimator = SmartFundEstimator()
    
    def get_fund_risk_metrics(self, fund_code: str) -> Optional[Dict]:
        """
        获取基金风险指标：夏普比率、年化波动率、最大回撤、同类排名
        """
        try:
            logger.info(f"\n[步骤4] 获取基金风险指标...")
            logger.info(f"  基金代码: {fund_code}")
            
            # 调用akshare接口获取风险指标数据
            logger.info(f"  调用ak.fund_individual_analysis_xq接口...")
            df = ak.fund_individual_analysis_xq(symbol=fund_code)
            
            logger.info(f"  接口返回数据类型: {type(df)}")
            if df is not None:
                logger.info(f"  接口返回数据形状: {df.shape}")
                logger.info(f"  接口返回数据前5行: {df.head().to_dict()}")
            
            if df is None or df.empty:
                logger.warning(f"无法获取基金 {fund_code} 风险指标数据")
                return None
            
            # 提取需要的数据
            risk_metrics = {
                'sharpe_ratio': None,
                'annual_volatility': None,
                'max_drawdown': None,
                'rank_1y': None,
                'rank_3y': None,
                'rank_5y': None
            }
            
            # 遍历数据行，提取所需指标
            logger.info(f"  开始提取风险指标数据...")
            for index, row in df.iterrows():
                period = str(row.get('周期', '')).strip()
                logger.info(f"  行 {index}: 周期={period}")
                
                if '近1年' in period:
                    # 提取近1年数据
                    try:
                        risk_metrics['sharpe_ratio'] = float(row.get('年化夏普比率', None))
                        logger.info(f"  提取近1年夏普比率成功: {risk_metrics['sharpe_ratio']}")
                    except Exception as e:
                        logger.warning(f"  提取近1年夏普比率失败: {e}")
                        pass
                    
                    try:
                        risk_metrics['annual_volatility'] = float(row.get('年化波动率', None))
                        logger.info(f"  提取近1年年化波动率成功: {risk_metrics['annual_volatility']}")
                    except Exception as e:
                        logger.warning(f"  提取近1年年化波动率失败: {e}")
                        pass
                    
                    try:
                        max_drawdown = float(row.get('最大回撤', None))
                        risk_metrics['max_drawdown'] = -max_drawdown  # 转换为负数表示下跌
                        logger.info(f"  提取近1年最大回撤成功: {risk_metrics['max_drawdown']}")
                    except Exception as e:
                        logger.warning(f"  提取近1年最大回撤失败: {e}")
                        pass
                    
                    try:
                        risk_metrics['rank_1y'] = str(row.get('较同类风险收益比', None))
                        logger.info(f"  提取近1年同类排名成功: {risk_metrics['rank_1y']}")
                    except Exception as e:
                        logger.warning(f"  提取近1年同类排名失败: {e}")
                        pass
                
                elif '近3年' in period:
                    # 提取近3年数据
                    try:
                        risk_metrics['rank_3y'] = str(row.get('较同类风险收益比', None))
                        logger.info(f"  提取近3年同类排名成功: {risk_metrics['rank_3y']}")
                    except Exception as e:
                        logger.warning(f"  提取近3年同类排名失败: {e}")
                        pass
                
                elif '近5年' in period:
                    # 提取近5年数据
                    try:
                        risk_metrics['rank_5y'] = str(row.get('较同类风险收益比', None))
                        logger.info(f"  提取近5年同类排名成功: {risk_metrics['rank_5y']}")
                    except Exception as e:
                        logger.warning(f"  提取近5年同类排名失败: {e}")
                        pass
            
            logger.info(f"  风险指标获取成功: {risk_metrics}")
            return risk_metrics
            
        except Exception as e:
            logger.error(f"获取基金风险指标失败 {fund_code}: {e}")
            import traceback
            logger.error(f"详细错误信息: {traceback.format_exc()}")
            return None
    
    def analyze_fund(self, fund_code: str, fund_name: str, holding: float) -> Optional[Dict]:
        """
        分析单只基金：估值 + 回撤(90日)
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"开始分析基金: {fund_code} ({fund_name})")
        logger.info(f"{'='*60}")
        
        # 1. 获取实时估值
        logger.info("\n[步骤1] 获取实时估值...")
        estimate_result = self.estimator.estimate_fund(fund_code, fund_name, holding)
        if not estimate_result:
            logger.error("  实时估值获取失败")
            return None
        
        today_change = estimate_result['estimate_change']
        
        # 2. 获取历史回撤（90日窗口）
        logger.info("\n[步骤2] 获取90日滚动高点回撤...")
        drawdown_result = get_fund_drawdown(fund_code, rolling_days=90, target_date=None)
        if not drawdown_result:
            logger.error("  历史回撤数据获取失败")
            return None
        
        # 强制转换所有numpy类型为Python原生类型
        historical_drawdown_pos = float(drawdown_result['drawdown_pct'])  # 正数表示下跌（如10.98）
        yesterday_nav = float(drawdown_result['current_nav'])
        rolling_high = float(drawdown_result['rolling_high'])
        
        # 转换为负数表示下跌（用于显示）
        historical_drawdown_neg = -historical_drawdown_pos  # -10.98
        
        # 3. 计算预估回撤（负数表示下跌）
        estimated_nav = yesterday_nav * (1 + today_change / 100)
        estimated_drawdown = (estimated_nav - rolling_high) / rolling_high * 100  # 负数（如-11.65）
        
        # 4. 获取风险指标
        risk_metrics = self.get_fund_risk_metrics(fund_code)
        
        # 确保risk_metrics不为None，而是一个空字典
        if risk_metrics is None:
            risk_metrics = {
                'sharpe_ratio': None,
                'annual_volatility': None,
                'max_drawdown': None,
                'rank_1y': None,
                'rank_3y': None,
                'rank_5y': None
            }
        
        logger.info(f"\n[步骤3] 计算合成指标...")
        logger.info(f"  昨日净值: {yesterday_nav}")
        logger.info(f"  90日高点: {rolling_high} ({drawdown_result['high_date']})")
        logger.info(f"  历史回撤: {historical_drawdown_neg:.2f}%")
        logger.info(f"  今日估值: {today_change:+.2f}%")
        logger.info(f"  预估净值: {estimated_nav:.4f}")
        logger.info(f"  预估回撤: {estimated_drawdown:.2f}%")
        logger.info(f"  风险指标: {risk_metrics}")
        
        # 5. 组装完整结果（确保所有类型可JSON序列化）
        result = {
            'fund_code': str(fund_code),
            'fund_name': str(fund_name),
            'holding': float(holding),
            
            'real_time_estimate': {
                'today_change_pct': float(estimate_result['estimate_change']),
                'estimated_nav': float(round(estimated_nav, 4)),
                'market': str(estimate_result.get('market', '未知')),
                'benchmark': str(estimate_result.get('benchmark', '未知')),
                'update_time': str(estimate_result.get('update_time', datetime.now().strftime('%H:%M:%S')))
            },
            
            'historical_drawdown': {
                'yesterday_nav': float(yesterday_nav),
                'rolling_high_90d': float(rolling_high),
                'high_date': str(drawdown_result['high_date']),
                'drawdown_to_high_pct': float(historical_drawdown_neg),  # 负数表示下跌
                'is_at_rolling_high': bool(abs(estimated_drawdown) < 0.01)
            },
            
            'synthetic_forecast': {
                'estimated_drawdown_pct': float(round(estimated_drawdown, 2)),  # 负数表示下跌
                'drawdown_change_today': float(round(estimated_drawdown - historical_drawdown_neg, 2))
            },
            
            'risk_metrics': risk_metrics,
            
            'raw_estimate_data': estimate_result
        }
        
        logger.info(f"\n[结果] {fund_code} 分析完成")
        
        return result


# ==========================================
# AI 服务层（仅用于解析基金输入）
# ==========================================

class AIService:
    """AI服务封装，仅用于解析自然语言输入"""
    
    @staticmethod
    def parse_funds_natural_language(text: str) -> List[Dict]:
        """
        使用AI解析自然语言输入，提取基金信息
        支持仅输入基金代码或基金名称，也支持不输入金额
        返回: [{"code": "...", "name": "...", "holding": ...}, ...]
        """
        if not ai_provider.is_configured():
            raise ValueError("AI服务未配置")
        
        # 清洗输入
        text = sanitize_input(text, max_length=3000)
        
        prompt = f"""请从以下文本中提取基金信息，返回标准JSON数组格式。每个对象可包含code(基金代码,6位数字)、name(基金名称)、holding(持仓金额,数字)。
重要规则：
1. 基金代码通常是6位数字，如果用户只输入名称没有代码，则code字段留空或省略
2. 如果用户只输入代码没有名称，则name字段留空或省略
3. 金额支持"元","块","万"等单位，转换为纯数字（如1.5万转换为15000）
4. 如果用户没有输入金额，holding字段可以为0、null或省略
5. 只返回JSON数组，不要任何其他文字、解释或markdown格式

文本：{text}

示例输出：
- 完整信息：[{{"code":"110011","name":"易方达蓝筹","holding":10000}}]
- 只有代码：[{{"code":"110011","holding":0}}]
- 只有名称：[{{"name":"易方达蓝筹","holding":0}}]
- 只有代码和金额：[{{"code":"110011","holding":5000}}]"""

        try:
            content = ai_provider.chat(prompt, temperature=0.1, max_tokens=2000, timeout=30)
            
            # 提取JSON数组
            json_match = re.search(r'\[[\s\S]*?\]', content)
            if not json_match:
                raise ValueError("AI返回格式错误")
            
            funds = json.loads(json_match[0])
            
            # 验证和清洗结果，并补全信息
            valid_funds = []
            for fund in funds:
                code = sanitize_fund_code(fund.get('code', ''))
                name = fund.get('name', '').strip()
                
                # 处理持仓金额
                try:
                    holding = float(fund.get('holding', 0) or 0)
                    if holding < 0:
                        holding = 0
                except:
                    holding = 0
                
                # 情况1: 有代码，可能有名称 - 直接使用
                if code:
                    # 如果没有名称，尝试从基金列表查找
                    if not name:
                        fund_info = FundSearchService.get_fund_by_code(code)
                        if fund_info:
                            name = fund_info['name']
                    
                    valid_funds.append({
                        'code': code,
                        'name': name[:50] if name else code,
                        'holding': holding
                    })
                
                # 情况2: 只有名称没有代码 - 搜索匹配的基金
                elif name and not code:
                    search_results = FundSearchService.search_fund(name, limit=5)
                    if search_results:
                        # 尝试精确匹配
                        matched = None
                        for result in search_results:
                            if result['name'] == name:
                                matched = result
                                break
                        # 如果没有精确匹配，使用第一个结果
                        if not matched:
                            matched = search_results[0]
                        
                        valid_funds.append({
                            'code': matched['code'],
                            'name': matched['name'],
                            'holding': holding
                        })
                        logger.info(f"通过名称搜索到基金: {name} -> {matched['code']} {matched['name']}")
                    else:
                        logger.warning(f"未找到与名称匹配的基金: {name}")
            
            return valid_funds
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误: {e}, 内容: {content}")
            raise ValueError("AI返回数据解析失败")
        except Exception as e:
            logger.error(f"AI解析错误: {e}")
            raise


# ==========================================
# 基金搜索服务
# ==========================================

class FundSearchService:
    """基金搜索服务 - 基于akshare基金列表"""
    
    _fund_list_cache = None
    _cache_time = None
    _cache_duration = 3600  # 缓存1小时
    
    # 列名常量（避免Windows编码问题）
    COL_CODE = '\u57fa\u91d1\u4ee3\u7801'  # 基金代码
    COL_NAME = '\u57fa\u91d1\u7b80\u79f0'  # 基金简称
    COL_PINYIN_ABBR = '\u62fc\u97f3\u7f29\u5199'  # 拼音缩写
    COL_TYPE = '\u57fa\u91d1\u7c7b\u578b'  # 基金类型
    COL_PINYIN_FULL = '\u62fc\u97f3\u5168\u79f0'  # 拼音全称
    
    # 倒排索引缓存
    _inverted_index = None
    _code_to_fund = None
    
    @classmethod
    def get_fund_list(cls) -> pd.DataFrame:
        """获取基金列表（带缓存）"""
        now = time.time()
        
        if cls._fund_list_cache is not None and cls._cache_time is not None:
            if now - cls._cache_time < cls._cache_duration:
                return cls._fund_list_cache
        
        try:
            df = ak.fund_name_em()
            cls._fund_list_cache = df
            cls._cache_time = now
            # 重建索引
            cls._build_indexes(df)
            logger.info(f"\u57fa\u91d1\u5217\u8868\u7f13\u5b58\u5df2\u66f4\u65b0\uff0c\u5171{len(df)}\u6761\u8bb0\u5f55")
            return df
        except Exception as e:
            logger.error(f"\u83b7\u53d6\u57fa\u91d1\u5217\u8868\u5931\u8d25: {e}")
            if cls._fund_list_cache is not None:
                return cls._fund_list_cache
            raise
    
    @classmethod
    def _build_indexes(cls, df: pd.DataFrame):
        """构建搜索索引"""
        cls._inverted_index = {}
        cls._code_to_fund = {}
        
        try:
            for idx, row in df.iterrows():
                try:
                    code = str(row[cls.COL_CODE])
                    name = str(row.get(cls.COL_NAME, '')).strip()
                    pinyin_abbr = str(row.get(cls.COL_PINYIN_ABBR, '')).strip().upper()
                    fund_type = str(row.get(cls.COL_TYPE, '')).strip()
                    
                    # 构建基金信息
                    fund_info = {
                        'code': code,
                        'name': name,
                        'pinyin': pinyin_abbr,
                        'type': fund_type
                    }
                    
                    # 代码到基金的映射
                    cls._code_to_fund[code] = fund_info
                    
                    # 构建倒排索引
                    # 1. 代码索引
                    for i in range(len(code)):
                        prefix = code[:i+1]
                        if prefix not in cls._inverted_index:
                            cls._inverted_index[prefix] = set()
                        cls._inverted_index[prefix].add(code)
                    
                    # 2. 名称索引
                    if name:
                        # 全名称
                        name_lower = name.lower()
                        for i in range(len(name_lower)):
                            for j in range(i+1, min(i+10, len(name_lower)+1)):
                                substr = name_lower[i:j]
                                if substr not in cls._inverted_index:
                                    cls._inverted_index[substr] = set()
                                cls._inverted_index[substr].add(code)
                    
                    # 3. 拼音缩写索引
                    if pinyin_abbr:
                        for i in range(len(pinyin_abbr)):
                            prefix = pinyin_abbr[:i+1]
                            if prefix not in cls._inverted_index:
                                cls._inverted_index[prefix] = set()
                            cls._inverted_index[prefix].add(code)
                            
                except Exception as e:
                    logger.debug(f"处理基金数据时出错: {e}")
                    continue
        except Exception as e:
            logger.error(f"构建索引时出错: {e}")
            cls._inverted_index = {}
            cls._code_to_fund = {}
    
    @classmethod
    def search_fund(cls, keyword: str, limit: int = 10) -> List[Dict]:
        """
        搜索基金（支持代码、名称、拼音模糊匹配）
        """
        if not keyword or len(keyword) < 2:
            return []
        
        keyword = str(keyword).strip()
        keyword_lower = keyword.lower()
        keyword_upper = keyword.upper()
        
        # 确保索引已构建
        if cls._inverted_index is None or cls._code_to_fund is None:
            df = cls.get_fund_list()
            if cls._inverted_index is None:
                # 如果索引仍然未构建，使用备用方案
                return cls._search_fund_fallback(df, keyword, limit)
        
        # 使用倒排索引搜索
        matched_codes = set()
        
        # 1. 精确代码匹配（如果是数字）
        if keyword.isdigit():
            if keyword in cls._code_to_fund:
                matched_codes.add(keyword)
        
        # 2. 前缀匹配
        if keyword_lower in cls._inverted_index:
            matched_codes.update(cls._inverted_index[keyword_lower])
        if keyword_upper in cls._inverted_index:
            matched_codes.update(cls._inverted_index[keyword_upper])
        
        # 3. 子串匹配（针对名称）
        if len(keyword) > 2:
            for key in list(cls._inverted_index.keys()):
                if keyword_lower in key.lower():
                    matched_codes.update(cls._inverted_index[key])
                if len(matched_codes) >= limit * 2:  # 提前终止
                    break
        
        # 4. 收集结果
        results = []
        seen_codes = set()
        
        for code in matched_codes:
            if code in cls._code_to_fund and code not in seen_codes:
                results.append(cls._code_to_fund[code])
                seen_codes.add(code)
                if len(results) >= limit:
                    break
        
        # 如果结果不足，使用备用方案
        if len(results) < limit:
            df = cls.get_fund_list()
            fallback_results = cls._search_fund_fallback(df, keyword, limit - len(results))
            
            # 添加未重复的结果
            for fund in fallback_results:
                if fund['code'] not in seen_codes:
                    results.append(fund)
                    seen_codes.add(fund['code'])
                    if len(results) >= limit:
                        break
        
        return results
    
    @classmethod
    def _search_fund_fallback(cls, df: pd.DataFrame, keyword: str, limit: int) -> List[Dict]:
        """备选搜索方案（使用列索引）"""
        keyword_upper = keyword.upper()
        results = []
        seen_codes = set()
        
        # 快速过滤：只处理可能匹配的行
        try:
            # 使用向量化操作快速过滤
            mask = (
                df[cls.COL_CODE].astype(str).str.contains(keyword, na=False, case=False, regex=False) |
                df[cls.COL_NAME].str.contains(keyword, na=False, case=False, regex=False) |
                df[cls.COL_PINYIN_ABBR].str.contains(keyword_upper, na=False, regex=False)
            )
            
            filtered_df = df[mask]
            
            for idx, row in filtered_df.iterrows():
                if len(results) >= limit:
                    break
                
                try:
                    code = str(row.iloc[0])  # 第0列：基金代码
                    if code in seen_codes:
                        continue
                    
                    name = str(row.iloc[2])  # 第2列：基金简称
                    pinyin_abbr = str(row.iloc[1])  # 第1列：拼音缩写
                    fund_type = str(row.iloc[3])  # 第3列：基金类型
                    
                    results.append({
                        'code': code,
                        'name': name,
                        'pinyin': pinyin_abbr,
                        'type': fund_type
                    })
                    seen_codes.add(code)
                except Exception as e:
                    logger.debug(f"处理搜索结果时出错: {e}")
                    continue
        except Exception as e:
            logger.error(f"备用搜索方案出错: {e}")
            # 极端情况：逐行处理
            for idx, row in df.iterrows():
                if len(results) >= limit:
                    break
                
                try:
                    code = str(row.iloc[0])
                    if code in seen_codes:
                        continue
                    
                    name = str(row.iloc[2])
                    pinyin_abbr = str(row.iloc[1])
                    
                    if (keyword in code or 
                        keyword in name or
                        keyword_upper in pinyin_abbr):
                        fund_type = str(row.iloc[3])
                        results.append({
                            'code': code,
                            'name': name,
                            'pinyin': pinyin_abbr,
                            'type': fund_type
                        })
                        seen_codes.add(code)
                except Exception as e:
                    logger.debug(f"逐行处理时出错: {e}")
                    continue
        
        return results
    
    @classmethod
    def get_fund_by_code(cls, fund_code: str) -> Optional[Dict]:
        """通过基金代码精确查询"""
        fund_code = str(fund_code).strip()
        
        # 优先使用代码映射
        if cls._code_to_fund and fund_code in cls._code_to_fund:
            return cls._code_to_fund[fund_code]
        
        # 备用方案
        df = cls.get_fund_list()
        
        try:
            result = df[df[cls.COL_CODE].astype(str) == fund_code]
            
            if result.empty:
                return None
            
            row = result.iloc[0]
            return {
                'code': str(row[cls.COL_CODE]),
                'name': str(row.get(cls.COL_NAME, '')),
                'pinyin': str(row.get(cls.COL_PINYIN_ABBR, '')),
                'type': str(row.get(cls.COL_TYPE, ''))
            }
        except Exception as e:
            logger.error(f"\u83b7\u53d6\u57fa\u91d1\u4fe1\u606f\u5931\u8d25: {e}")
            # 备选方案
            for idx, row in df.iterrows():
                try:
                    if str(row.iloc[0]) == fund_code:
                        return {
                            'code': str(row.iloc[0]),
                            'name': str(row.iloc[2]),
                            'pinyin': str(row.iloc[1]),
                            'type': str(row.iloc[3])
                        }
                except Exception as e:
                    logger.debug(f"逐行查询时出错: {e}")
                    continue
            return None


# ==========================================
# Flask API 路由
# ==========================================

estimator = SmartFundEstimator()
fund_analyzer = FundAnalyzer()
ai_service = AIService()

@app.route('/api/search_fund', methods=['GET'])
@limiter.limit("60 per minute")
def search_fund():
    """
    基金搜索接口（支持代码、名称、拼音模糊匹配）
    请求: GET /api/search_fund?keyword=白酒&limit=10
    响应: {"results": [{"code": "...", "name": "...", "pinyin": "...", "type": "..."}]}
    """
    keyword = request.args.get('keyword', '').strip()
    limit = request.args.get('limit', 10, type=int)
    
    if not keyword:
        return jsonify({'error': '缺少keyword参数'}), 400
    
    if len(keyword) < 2:
        return jsonify({'error': '关键词至少2个字符'}), 400
    
    if limit < 1 or limit > 20:
        limit = 10
    
    try:
        results = FundSearchService.search_fund(keyword, limit)
        return jsonify({
            'success': True,
            'keyword': keyword,
            'results': results,
            'count': len(results)
        })
    except Exception as e:
        logger.error(f"搜索基金错误: {e}")
        return jsonify({'error': '搜索服务暂时不可用'}), 503


@app.route('/api/fund_info/<fund_code>', methods=['GET'])
@limiter.limit("60 per minute")
def fund_info(fund_code):
    """
    获取基金基本信息
    请求: GET /api/fund_info/110011
    响应: {"code": "...", "name": "...", "pinyin": "...", "type": "..."}
    """
    code = sanitize_fund_code(fund_code)
    if not code:
        return jsonify({'error': '无效的基金代码'}), 400
    
    try:
        result = FundSearchService.get_fund_by_code(code)
        if result:
            return jsonify({
                'success': True,
                'fund': result
            })
        else:
            return jsonify({'error': '基金未找到'}), 404
    except Exception as e:
        logger.error(f"获取基金信息错误: {e}")
        return jsonify({'error': '服务暂时不可用'}), 503


@app.route('/api/parse_funds', methods=['POST'])
@limiter.limit("10 per minute")  # 限制AI解析频率（成本较高）
def parse_funds():
    """
    AI智能解析基金信息
    请求: {"text": "用户输入的自然语言文本"}
    响应: {"funds": [{"code": "...", "name": "...", "holding": ...}]}
    """
    try:
        data = request.get_json()
        if not data or 'text' not in data:
            return jsonify({'error': '缺少text参数'}), 400
        
        text = data['text']
        if not text or len(text) > 3000:
            return jsonify({'error': '文本为空或过长'}), 400
        
        funds = ai_service.parse_funds_natural_language(text)
        
        return jsonify({
            'success': True,
            'funds': funds,
            'count': len(funds)
        })
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"解析基金错误: {e}")
        return jsonify({'error': '解析服务暂时不可用'}), 503


@app.route('/api/estimate', methods=['POST'])
@limiter.limit("30 per minute")
def estimate():
    """仅估值接口"""
    data = request.get_json()
    funds = data.get('funds', [])
    
    # 验证输入
    is_valid, msg = validate_funds_data(funds)
    if not is_valid:
        return jsonify({'error': msg}), 400
    
    logger.info(f"\n开始估算 {len(funds)} 只基金 [v6.0 精简版]")
    
    results = []
    for fund in funds:
        try:
            result = estimator.estimate_fund(
                fund['code'],
                fund.get('name', fund['code']),
                fund['holding']
            )
            if result:
                results.append(result)
            time.sleep(0.5)  # 降低请求频率
        except Exception as e:
            logger.error(f"处理错误: {e}")
    
    if results:
        total_holding = sum(r['holding'] for r in results)
        total_profit = sum(r['profit'] for r in results)
        portfolio_change = total_profit / total_holding * 100 if total_holding > 0 else 0
        
        return jsonify({
            'results': results,
            'summary': {
                'total_holding': float(total_holding),
                'total_profit': float(round(total_profit, 2)),
                'portfolio_change': float(round(portfolio_change, 2))
            }
        })
    
    return jsonify({'results': [], 'summary': {}})


@app.route('/api/fund_analysis', methods=['POST'])
@limiter.limit("20 per minute")
def fund_analysis():
    """
    基金分析接口：估值 + 回撤（90日高点）
    不包含投资建议和网格策略
    使用并行处理提升性能
    """
    data = request.get_json()
    funds = data.get('funds', [])
    
    # 验证输入
    is_valid, msg = validate_funds_data(funds)
    if not is_valid:
        return jsonify({'error': msg}), 400
    
    logger.info(f"\n{'#'*70}")
    logger.info(f"启动基金分析 - 共{len(funds)}只基金（并行处理版）")
    logger.info(f"{'#'*70}")
    
    results = []
    
    def analyze_single_fund(fund):
        try:
            result = fund_analyzer.analyze_fund(
                fund['code'],
                fund.get('name', fund['code']),
                float(fund.get('holding', 0))
            )
            return result
        except Exception as e:
            logger.error(f"分析基金 {fund['code']} 时出错: {e}")
            return None
    
    # 使用线程池并行处理，最多5个并发
    max_workers = min(5, len(funds))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_fund = {executor.submit(analyze_single_fund, fund): fund for fund in funds}
        
        for future in as_completed(future_to_fund):
            result = future.result()
            if result:
                results.append(result)
    
    summary = {
        'total_funds': int(len(funds)),
        'analyzed_successfully': int(len(results)),
        'timestamp': str(datetime.now().isoformat())
    }
    
    return jsonify({
        'summary': summary,
        'detailed_results': results
    })


@app.route('/api/drawdown', methods=['POST'])
@limiter.limit("30 per minute")
def drawdown():
    """仅回撤分析接口（默认90日窗口）"""
    data = request.get_json()
    funds = data.get('funds', [])
    rolling_days = int(data.get('rolling_days', 90))
    
    if rolling_days not in [30, 60, 90, 120, 250]:
        return jsonify({'error': '不支持的回撤窗口期'}), 400
    
    results = []
    for fund in funds:
        try:
            code = sanitize_fund_code(fund['code'])
            if not code:
                continue
                
            result = get_fund_drawdown(
                code,
                rolling_days=rolling_days,
                target_date=fund.get('target_date')
            )
            if result:
                # 转换回撤为负数表示下跌
                result['drawdown_pct'] = -float(result['drawdown_pct'])
                results.append(result)
        except Exception as e:
            logger.error(f"获取回撤数据失败 {fund.get('code')}: {e}")
    
    return jsonify({
        'rolling_window': f"{rolling_days}日",
        'results': results,
        'count': int(len(results))
    })


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok', 
        'version': '6.4 Compare-Edition', 
        'time': str(datetime.now().isoformat()),
        'modules': ['estimate', 'drawdown', 'fund_analysis', 'ai_parse', 'fund_search', 'nav_history', 'nav_history_batch'],
        'default_window': '90d',
        'ai_enabled': ai_provider.is_configured(),
        'ai_provider': ai_provider.get_info(),
        'note': '支持手动输入、基金搜索、本地缓存、净值走势图表、批量对比分析'
    })


@app.route('/api/get_indices', methods=['GET'])
@limiter.limit('30 per minute')
def get_indices():
    """
    获取实时指数涨跌幅
    """
    try:
        indices = []
        
        # 获取所有支持的指数
        for index_name, code in estimator.index_codes.items():
            try:
                change = estimator.get_index_change(index_name)
                indices.append({
                    'name': index_name,
                    'code': code,
                    'change': float(round(change, 2))
                })
            except Exception as e:
                logger.error(f"获取{index_name}数据失败: {e}")
                # 继续处理其他指数，不返回模拟数据
                indices.append({
                    'name': index_name,
                    'code': code,
                    'change': None,
                    'error': str(e)
                })
        
        return jsonify({
            'success': True,
            'indices': indices,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        logger.error(f"API错误: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@app.route('/api/get_nav_history', methods=['GET'])
@limiter.limit('30 per minute')
def get_nav_history():
    """
    获取基金历史净值数据
    GET: /api/get_nav_history?code=110011&days=90
    """
    try:
        fund_code = request.args.get('code', '')
        days = request.args.get('days', 90, type=int)
        
        if not fund_code:
            return jsonify({'error': '缺少基金代码'}), 400
        
        fund_code = sanitize_fund_code(fund_code)
        if not fund_code:
            return jsonify({'error': '基金代码格式错误'}), 400
        
        if days not in [30, 60, 90, 180, 365]:
            days = 90
        
        try:
            df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
        except Exception as e:
            logger.error(f"获取净值数据失败 {fund_code}: {e}")
            return jsonify({
                'success': False,
                'message': f'获取净值数据失败: {str(e)}'
            })
        
        if df is None or df.empty:
            return jsonify({
                'success': False,
                'message': '无法获取基金净值数据'
            })
        
        df = df.iloc[:, :2].copy()
        df.columns = ['date', 'nav']
        df['date'] = pd.to_datetime(df['date'])
        df['nav'] = pd.to_numeric(df['nav'], errors='coerce')
        df = df.dropna().sort_values('date')
        
        recent_df = df.tail(days)
        
        dates = recent_df['date'].dt.strftime('%Y-%m-%d').tolist()
        navs = recent_df['nav'].round(4).tolist()
        
        if len(navs) > 0:
            max_nav = float(recent_df['nav'].max())
            min_nav = float(recent_df['nav'].min())
            current_nav = float(navs[-1])
            start_nav = float(navs[0])
            total_return = ((current_nav - start_nav) / start_nav * 100) if start_nav > 0 else 0
            
            max_date = recent_df[recent_df['nav'] == recent_df['nav'].max()]['date'].iloc[-1].strftime('%Y-%m-%d')
            min_date = recent_df[recent_df['nav'] == recent_df['nav'].min()]['date'].iloc[-1].strftime('%Y-%m-%d')
        else:
            max_nav = min_nav = current_nav = start_nav = total_return = 0
            max_date = min_date = ''
        
        return jsonify({
            'success': True,
            'fund_code': fund_code,
            'days': days,
            'data': {
                'dates': dates,
                'navs': navs
            },
            'statistics': {
                'max_nav': round(max_nav, 4),
                'max_date': max_date,
                'min_nav': round(min_nav, 4),
                'min_date': min_date,
                'current_nav': round(current_nav, 4),
                'total_return': round(total_return, 2),
                'data_points': len(navs)
            },
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        logger.error(f"API错误: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@app.route('/api/get_nav_history_batch', methods=['GET'])
@limiter.limit('20 per minute')
def get_nav_history_batch():
    """
    批量获取多只基金历史净值数据（用于对比分析）
    GET: /api/get_nav_history_batch?codes=110011,110022,110033&days=90
    """
    try:
        codes_param = request.args.get('codes', '')
        days = request.args.get('days', 180, type=int)
        
        if not codes_param:
            return jsonify({'error': '缺少基金代码'}), 400
        
        codes = [sanitize_fund_code(c.strip()) for c in codes_param.split(',') if c.strip()]
        codes = [c for c in codes if c]
        
        if not codes:
            return jsonify({'error': '没有有效的基金代码'}), 400
        
        if len(codes) > 4:
            return jsonify({'error': '最多支持4只基金对比'}), 400
        
        if days not in [30, 90, 180, 365]:
            days = 180
        
        results = []
        
        def fetch_single_fund(fund_code):
            try:
                df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
                
                if df is None or df.empty:
                    return None
                
                df = df.iloc[:, :2].copy()
                df.columns = ['date', 'nav']
                df['date'] = pd.to_datetime(df['date'])
                df['nav'] = pd.to_numeric(df['nav'], errors='coerce')
                df = df.dropna().sort_values('date')
                
                recent_df = df.tail(days)
                
                dates = recent_df['date'].dt.strftime('%Y-%m-%d').tolist()
                navs = recent_df['nav'].round(4).tolist()
                
                if len(navs) > 0:
                    max_nav = float(recent_df['nav'].max())
                    min_nav = float(recent_df['nav'].min())
                    current_nav = float(navs[-1])
                    start_nav = float(navs[0])
                    total_return = ((current_nav - start_nav) / start_nav * 100) if start_nav > 0 else 0
                else:
                    max_nav = min_nav = current_nav = start_nav = total_return = 0
                
                return {
                    'code': fund_code,
                    'data': {
                        'dates': dates,
                        'navs': navs
                    },
                    'statistics': {
                        'max_nav': round(max_nav, 4),
                        'min_nav': round(min_nav, 4),
                        'current_nav': round(current_nav, 4),
                        'total_return': round(total_return, 2),
                        'data_points': len(navs)
                    }
                }
            except Exception as e:
                logger.error(f"获取基金 {fund_code} 净值数据失败: {e}")
                return None
        
        with ThreadPoolExecutor(max_workers=min(4, len(codes))) as executor:
            future_to_code = {executor.submit(fetch_single_fund, code): code for code in codes}
            
            for future in as_completed(future_to_code):
                result = future.result()
                if result:
                    results.append(result)
        
        return jsonify({
            'success': True,
            'funds': results,
            'days': days,
            'count': len(results),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        logger.error(f"批量获取净值数据API错误: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@app.route('/api/get_fund_detail', methods=['GET'])
@limiter.limit('10 per minute')
def get_fund_detail():
    """
    获取基金详情，包括实时持仓股票涨跌幅和加权计算
    GET: /api/get_fund_detail?code=110011
    """
    try:
        fund_code = request.args.get('code', '')
        if not fund_code:
            return jsonify({'error': '缺少基金代码'}), 400
        
        fund_code = sanitize_fund_code(fund_code)
        if not fund_code:
            return jsonify({'error': '基金代码格式错误'}), 400
        
        # 获取基金持仓数据
        try:
            df = ak.fund_portfolio_hold_em(symbol=fund_code, date="2025")
            if df.empty:
                df = ak.fund_portfolio_hold_em(symbol=fund_code, date="2024")
            
            if df.empty:
                return jsonify({
                    'success': False,
                    'message': '无法获取基金持仓数据'
                })
            
            # 获取最新季度数据
            latest_q = sorted(df['季度'].unique(), reverse=True)[0]
            data = df[df['季度'] == latest_q].head(10)
            
            # 处理持仓数据
            holdings = []
            codes = []
            names = []
            total_ratio = 0
            
            for _, row in data.iterrows():
                code = str(row['股票代码'])
                name = str(row['股票名称'])
                ratio = float(row['占净值比例'])
                
                holdings.append({
                    'code': code,
                    'name': name,
                    'ratio': ratio
                })
                codes.append(code)
                names.append(name)
                total_ratio += ratio
            
            # 获取股票实时涨跌幅
            changes = estimator.get_stock_changes(codes, names)
            
            # 计算加权贡献
            for holding in holdings:
                holding['change'] = changes.get(holding['code'], 0)
                holding['contribution'] = holding['change'] * holding['ratio'] / 100
            
            # 计算基准指数涨跌幅
            market, benchmark, est_position = estimator.detect_market_and_benchmark(data, "")
            bench_chg = estimator.get_index_change(benchmark)
            
            # 计算剩余部分贡献
            remaining_ratio = max(0, est_position * 100 - total_ratio)
            remaining_contrib = bench_chg * (remaining_ratio / 100)
            
            # 计算总涨跌幅
            total_change = sum(h['contribution'] for h in holdings) + remaining_contrib
            
            return jsonify({
                'success': True,
                'fund_code': fund_code,
                'holdings': holdings,
                'total_ratio': float(round(total_ratio, 2)),
                'remaining_ratio': float(round(remaining_ratio, 2)),
                'benchmark': benchmark,
                'benchmark_change': float(round(bench_chg, 2)),
                'total_change': float(round(total_change, 2)),
                'calculation_method': '加权平均: 持仓股票涨跌幅 × 占比 + 剩余部分使用基准指数涨跌幅',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            
        except Exception as e:
            logger.error(f"获取基金详情失败: {e}")
            return jsonify({
                'success': False,
                'message': str(e)
            })
        
    except Exception as e:
        logger.error(f"API错误: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


# 全局错误处理
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': '接口不存在'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"服务器错误: {error}")
    return jsonify({'error': '服务器内部错误'}), 500

@app.errorhandler(429)
def ratelimit_handler(error):
    return jsonify({'error': '请求过于频繁，请稍后再试'}), 429


if __name__ == '__main__':
    print("="*70)
    print("基金估值与回撤系统 v6.2 - 手动输入版")
    print("功能：估值显示 + 滚动回撤 + 基金搜索 + 本地缓存")
    print("接口列表：")
    print("  - GET  /api/search_fund      基金搜索（支持代码/名称/拼音）")
    print("  - GET  /api/fund_info/<code> 获取基金基本信息")
    print("  - POST /api/parse_funds      AI解析自然语言")
    print("  - POST /api/fund_analysis    基金分析（估值+回撤）")
    print("  - POST /api/estimate         仅估值")
    print("  - POST /api/drawdown         仅回撤")
    print("  - GET  /api/health           健康检查")
    print("="*70)
    
    # 生产环境请设置 debug=False
    app.run(debug=False, port=5000, host='0.0.0.0')
