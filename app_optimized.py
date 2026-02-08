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