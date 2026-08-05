import numpy as np
import pandas as pd
import inspect
from qlib.data.ops import ElemOperator  , Rolling , Feature , XSectionOperator
from qlib.data.base import Expression
import pandas as pd
import numpy as np
from qlib.data.ops import ElemOperator
from qlib.data import D 
import threading
from src.config import RuntimeConfig
from collections import defaultdict
# 橫截面算子抽象基類


class CSRank(XSectionOperator):
    def _process_df(self, df, **_) -> pd.DataFrame:
        print('處理CSRank')
        return df.rank(axis=1, pct=True)


class CSScale(XSectionOperator):
    def _process_df(self, df, **_) -> pd.DataFrame:
        return df.div(df.abs().sum(axis=1), axis=0)

            
            
# 如果 exponent 也是一個特徵 (如 Alpha#084)
class SignedPower(ElemOperator):
    """
    Args:
        feature: 特徵
        exponent_feature: 指數特徵（可以是 Expression 或 float）
    動態指數排序
    正負號不變 取指數
    """
    def __init__(self, feature, exponent_feature):
        # 如果指數是 float 或 int，直接保存；否則作為 Expression 處理
        if isinstance(exponent_feature, (int, float)):
            self.exponent_feature = exponent_feature
            self.is_constant = True
        else:
            self.exponent_feature = exponent_feature
            self.is_constant = False
        super().__init__(feature)
    def __str__(self):
        return "{}({},{})".format(type(self).__name__, self.feature, self.exponent_feature)

    def _load_internal(self, instrument, start_index, end_index, freq):
        x = self.feature.load(instrument, start_index, end_index, freq)
        if self.is_constant:
        
            a = self.exponent_feature
        else:
            a = self.exponent_feature.load(instrument, start_index, end_index, freq)
        return np.sign(x) * (np.abs(x) ** a)

class Prod(Rolling):
    """
    時序滾動乘積：基於你提供的 Rolling 基類實作
    """
    def __init__(self, feature, N):
        # 既然父類別 Rolling.__init__ 需要 (feature, N, func)
        # 我們直接把 "prod" 傳進去即可
        # Pandas 的 Rolling 對象原生支援 .prod() 方法
        super(Prod, self).__init__(feature, N, "prod")


class ts_backfill(ElemOperator):
    """以前一筆有效值填補缺失值，避免使用未來資料。"""

    def _load_internal(self, instrument, start_index, end_index, freq):
        return self.feature.load(instrument, start_index, end_index, freq).ffill()


# class IndNeutralize(BaseCrossSectionalOperator):
#     """
#     行業中性化算子 (高速矩陣版)
#     用法：IndNeutralize($close, "subindustry")
#     """
#     ALLOWED_LEVELS = ['exchange', 'industry', 'subindustry']

#     def __init__(self, feature, level):
#         if level not in self.ALLOWED_LEVELS:
#             raise ValueError(f"錯誤的分類層級: '{level}'。僅允許: {self.ALLOWED_LEVELS}")
#         self.level = level
#         # 建立行業特徵對象，用於在 apply_operator 中載入
#         self.industry_feat = Feature(level)
#         super(IndNeutralize, self).__init__(feature)

#     def _get_cache_key(self, start_index, end_index, freq):
#         # 快取鍵必須包含 level，防止不同層級混淆
#         return f"IndNeut_{self.level}_{str(self.feature)}_{start_index}_{end_index}"

#     def apply_operator(self, df: pd.DataFrame) -> pd.DataFrame:
#         """
#         df: index=datetime, columns=instrument, values=因子值
#         """
#         # 1. 獲取當前的全市場清單與時間索引
#         all_inst = df.columns.tolist()
#         start_idx = df.index[0]
#         end_idx = df.index[-1]

#         # 2. 載入對應的行業代碼矩陣 (同樣利用 RAMDisk 加速)
#         # 注意：這裡使用內建的 load 確保索引與 df 完全一致
#         ind_series = self.industry_feat.load(all_inst, start_idx, end_idx, df.index.freq)
#         ind_df = ind_series.unstack(level='instrument')

#         # 3. 執行橫截面中性化
#         # 我們將兩個矩陣融合，按 datetime (axis 0) 和 industry 進行分組
#         # 為了效能，我們對每一天進行處理
#         def neutralize_row(row_idx):
#             val_row = df.iloc[row_idx]
#             ind_row = ind_df.iloc[row_idx]
#             # 分組去均值：x - mean(x_in_industry)
#             return val_row - val_row.groupby(ind_row).transform('mean')

#         # 使用向量化方式處理所有日期
#         neutralized_df = pd.DataFrame(
#             [neutralize_row(i) for i in range(len(df))],
#             index=df.index,
#             columns=df.columns
#         )
        
#        return neutralized_df









#==================== 自動提取本檔案中定義的所有算子類別 ====================
def get_my_ops():
    """自動提取本檔案中定義的所有算子類別"""
    current_module = inspect.getmodule(inspect.currentframe())
    ops = []
    for name, obj in inspect.getmembers(current_module):
        # 條件：是類別、定義在本模組、繼承自 Expression、且不是 Expression 本身
        if (inspect.isclass(obj) and 
            obj.__module__ == __name__ and 
            issubclass(obj, Expression) and 
            obj is not Expression):
            ops.append(obj)
    return ops

# 預先生成列表，方便外部調用
all_custom_ops = get_my_ops()