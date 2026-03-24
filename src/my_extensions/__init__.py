# # my_extensions/__init__.py
# from qlib.data.ops import Operators
# from my_extensions.custom_ops import CSRank, Ts_Rank


# # 在模組被導入時立即執行註冊
# if 'CSRank' not in Operators._ops:
#     Operators.register([CSRank, Ts_Rank])
# # Operators.register([CSRank, Ts_Rank])
#     print("Successfully registered custom operators: CSRank, Ts_Rank")