"""
測試 Alpha 因子表達式是否能被 FactorEngine (alphagen) 的 ExpressionParser 正確解析。

不需要載入任何行情資料，只驗證語法 / 算子 / 參數合法性。
"""

import sys
from pathlib import Path

import pandas as pd

# ── 暫時加入 alphagen 路徑，以便 import ────────────────────────
_ALPHAGEN_ROOT = Path("/home/newt/alphagen/alphagen-master/alphagen-master")
_path_added = False
if _ALPHAGEN_ROOT.exists():
    _root_str = str(_ALPHAGEN_ROOT)
    if _root_str not in sys.path:
        sys.path.insert(0, _root_str)
        _path_added = True

from alphagen.data.expression import Expression, Operator
from alphagen.data.expressions import Operators
from alphagen.data.expressions.binary import Greater, Less, Pow, Eq
from alphagen.data.expressions.rolling import Ts_ArgMax, Ts_ArgMin
from alphagen.data.parser import ExpressionParser, ExpressionParsingError

# 載入完成後移除路徑
if _path_added:
    sys.path.remove(_root_str)

from src.alphas.alpha101 import Alpha101
from src.alphas.alpha191 import Alpha191


def _build_parser() -> ExpressionParser:
    """
    建立與 FactorEngine 相同設定的 ExpressionParser，
    僅用於語法驗證，不需要載入資料。
    """
    return ExpressionParser(
        Operators,
        ignore_case=True,
        non_positive_time_deltas_allowed=False,
    )


def test_alpha_expressions(alpha_class, parser: ExpressionParser) -> pd.DataFrame:
    """
    驗證 alpha_class 中所有因子表達式是否能被 ExpressionParser 正確解析。

    Parameters
    ----------
    alpha_class : class
        含有 get_all_factors() 的因子類別（如 Alpha101, Alpha191）。
    parser : ExpressionParser
        alphagen 的表達式解析器。

    Returns
    -------
    pd.DataFrame
        每筆因子的解析結果（Factor / Status / Expression / Error）。
    """
    results = []
    all_alphas = alpha_class.get_all_factors()
    class_name = alpha_class.__name__
    print(f"開始測試 {class_name}，共 {len(all_alphas)} 個因子表達式...\n")

    for name, expression_str in all_alphas.items():
        is_valid = False
        error_msg = ""

        try:
            parsed_expr = parser.parse(expression_str)

            if not isinstance(parsed_expr, Expression):
                is_valid = False
                error_msg = f"解析結果非 Expression 實例，而是 {type(parsed_expr).__name__}"
            else:
                is_valid = True

        except ExpressionParsingError as e:
            is_valid = False
            error_msg = f"解析錯誤: {e}"
        except NameError as e:
            is_valid = False
            error_msg = f"未定義: {e}"
        except SyntaxError as e:
            is_valid = False
            error_msg = f"語法錯誤: {e}"
        except TypeError as e:
            is_valid = False
            error_msg = f"類型錯誤: {e}"
        except Exception as e:
            is_valid = False
            error_msg = f"未預期錯誤 ({type(e).__name__}): {e}"

        results.append({
            "Factor": name,
            "Status": "PASS" if is_valid else "FAIL",
            "Expression": expression_str[:80] + "..." if len(expression_str) > 80 else expression_str,
            "Error": error_msg,
        })

    df_res = pd.DataFrame(results)

    # 印出失敗的項目
    failed = [r for r in results if r["Status"] == "FAIL"]
    for r in failed:
        print(f"  FAIL  {r['Factor']}")
        print(f"        {r['Error']}")
        print(f"        expr: {r['Expression']}\n")

    # 統計
    fail_count = len(failed)
    pass_count = len(results) - fail_count
    print(f"[{class_name}] 結果: {pass_count} PASS / {fail_count} FAIL (共 {len(results)} 個)")
    if fail_count == 0:
        print(f"[{class_name}] 所有因子語法檢查通過！\n")
    else:
        print(f"[{class_name}] 共有 {fail_count} 個因子存在語法錯誤，請檢查上方輸出。\n")

    return df_res


if __name__ == "__main__":
    parser = _build_parser()

    df_101 = pd.DataFrame()
    df_191 = pd.DataFrame()

    # print("=" * 60)
    # print("Testing Alpha101")
    # print("=" * 60)
    # df_101 = test_alpha_expressions(Alpha101, parser)
    
    print("=" * 60)
    print("Testing Alpha191")
    print("=" * 60)
    df_191 = test_alpha_expressions(Alpha191, parser)
    
    # 合併輸出總表（可選）
    df_all = pd.concat(
        [df_101.assign(Source="Alpha101"), df_191.assign(Source="Alpha191")],
        ignore_index=True,
    )
    total_fail = (df_all["Status"] == "FAIL").sum()
    total_pass = (df_all["Status"] == "PASS").sum()
    print("=" * 60)
    print(f"總計: {total_pass} PASS / {total_fail} FAIL (共 {len(df_all)} 個)")
    print("=" * 60)
