"""

將 WQ用的算子名稱與Qlib算同步
"""

from qlib.data.ops import Rank ,  IdxMax ,Min , Max , Ref , WMA
from qlib.data.base import Expression
import inspect
# 1. 將 WQ用的算子名稱與Qlib算同步
class Ts_Rank(Rank):
    pass

class Ts_ArgMax(IdxMax):
    pass

class Ts_Min(Min):
    pass

class Ts_Max(Max):
    pass

class Delay(Ref):
    pass


class Decay_linear(WMA):
    pass




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
all_rename_ops = get_my_ops()