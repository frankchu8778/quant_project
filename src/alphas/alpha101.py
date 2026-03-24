
SKIP_ALPHAS = frozenset({
    "alpha003", "alpha005", "alpha006", "alpha007" , "alpha008" , "alpha009" ,"alpha010"
    "alpha011" , "alpha012" , "alpha014" , "alpha015" , "alpha016" , "alpha017" , "alpha018" , 
    })


class Alpha101:
    """
    儲存 Alpha 101 表達式的倉庫
    每個方法回傳一個純前綴語法（prefix notation）字串表達式，
    供 alphagen ExpressionParser 解析。

    轉換規則：
      a + b  → Add(a, b)       a - b  → Sub(a, b)
      a * b  → Mul(a, b)       a / b  → Div(a, b)
      a < b  → Lt(a, b)        a > b  → Gt(a, b)
      a <= b → Le(a, b)        a >= b → Ge(a, b)
      Power  → Pow              Delay  → Ref
      IdxMax → Ts_ArgMax        IdxMin → Ts_ArgMin
      Decay_linear → WMA        Rank   → Ts_Rank
      vwap   → SafeDiv($amount, $volume)
      returns → Sub(Div($close, Ref($close, 1)), 1)
    """

    # 基礎資料欄位映射 (方便統一修改)
    C = "$close"
    O = "$open"
    H = "$high"
    L = "$low"
    V = "$volume"
    VWAP = "SafeDiv($amount, $volume)"
    CAP = "$cap"

    # ── alpha001 ~ alpha010 已通過測試 ──────────────────────────

    @classmethod
    def alpha001(cls):
        return "Sub(CSRank(Ts_ArgMax(SignedPower(If(Gt($return_day, 0), Std($return_day, 20), $close), 2), 5)), 0.5)"

    @classmethod
    def alpha002(cls):
        return "Mul(-1, Corr(CSRank(Delta(Log($volume), 2)), CSRank(Div(Sub($close, $open), $open)), 6))"

    @classmethod
    def alpha003(cls):
        # 爛透了，不要用
        return "Mul(-1, Corr(CSRank($open), CSRank($volume), 10))"

    @classmethod
    def alpha004(cls):
        return "Mul(-1, Ts_Rank(CSRank($low), 9))"

    @classmethod
    def alpha005(cls):
        # 爛透了，不要用
        return "Mul(CSRank(Sub($open, Mean(SafeDiv($amount, $volume), 10))), Mul(-1, Abs(CSRank(Sub($close, SafeDiv($amount, $volume))))))"

    @classmethod
    def alpha006(cls):
        # 爛透了，不要用
        return "Mul(-1, Corr($open, $volume, 10))"

    @classmethod
    def alpha007(cls):
        # 爛透了，不要用
        return "If(Lt(Mean($volume, 20), $volume), Mul(-1, Mul(Ts_Rank(Abs(Delta($close, 7)), 60), Sign(Delta($close, 7)))), -1)"

    @classmethod
    def alpha008(cls):
        # 爛透了，不要用
        return "Mul(-1, CSRank(Sub(Mul(Sum($open, 5), Sum(Sub(Div($close, Ref($close, 1)), 1), 5)), Ref(Mul(Sum($open, 5), Sum(Sub(Div($close, Ref($close, 1)), 1), 5)), 10))))"

    @classmethod
    def alpha009(cls):
        # 爛透了，不要用
        return "If(Gt(Ts_Min(Delta($close, 1), 5), 0), Delta($close, 1), If(Lt(Ts_Max(Delta($close, 1), 5), 0), Delta($close, 1), Mul(-1, Delta($close, 1))))"

    @classmethod
    def alpha010(cls):
        return "CSRank(If(Gt(Ts_Min(Delta($close, 1), 4), 0), Delta($close, 1), If(Lt(Ts_Max(Delta($close, 1), 4), 0), Delta($close, 1), Mul(-1, Delta($close, 1)))))"

    @classmethod
    def alpha011(cls):
        # (rank(ts_max(vwap-close,3)) + rank(ts_min(vwap-close,3))) * rank(delta(volume,3))
        return "Mul(Add(CSRank(Ts_Max(Sub(SafeDiv($amount, $volume), $close), 3)), CSRank(Ts_Min(Sub(SafeDiv($amount, $volume), $close), 3))), CSRank(Delta($volume, 3)))"

    @classmethod
    def alpha012(cls):
        # sign(delta(volume,1)) * (-1 * delta(close,1))
        return "Mul(Sign(Delta($volume, 1)), Mul(-1, Delta($close, 1)))"

    @classmethod
    def alpha013(cls):
        return "CSRANK(Mul(-1, CSRank(Cov(CSRank($close), CSRank($volume), 5))))"

    @classmethod
    def alpha014(cls):
        # -1 * rank(delta(returns,3)) * correlation(open, volume, 10)
        return "Mul(Mul(-1, CSRank(Delta(Sub(Div($close, Ref($close, 1)), 1), 3))), Corr($open, $volume, 10))"

    @classmethod
    def alpha015(cls):
        return "Mul(-1, Sum(CSRank(Corr(CSRank($high), CSRank($volume), 3)), 3))"

    @classmethod
    def alpha016(cls):
        return "Mul(-1, CSRank(Cov(CSRank($high), CSRank($volume), 5)))"

    @classmethod
    def alpha017(cls):
        # -1 * rank(Ts_Rank(close,10)) * rank(delta(delta(close,1),1)) * rank(Ts_Rank(volume,10))
        return "Mul(-1, Mul(Mul(CSRank(Ts_Rank($close, 10)), CSRank(Delta(Delta($close, 1), 1))), CSRank(Ts_Rank($volume, 10))))"

    @classmethod
    def alpha018(cls):
        # -1 * rank(stddev(abs(close-vwap),5) + (close-vwap) + corr(close,volume,6))
        return "Mul(-1, CSRank(Add(Add(Std(Abs(Sub($close, SafeDiv($amount, $volume))), 5), Sub($close, SafeDiv($amount, $volume))), Corr($close, $volume, 6))))"

    @classmethod
    def alpha019(cls):
        # -1 * sign(close-delay(close,7)) * (1 + rank(1 + sum(returns,250)))
        return "Mul(-1, Mul(Sign(Sub($close, Ref($close, 7))), Add(1, CSRank(Add(1, Sum(Sub(Div($close, Ref($close, 1)), 1), 250))))))"

    @classmethod
    def alpha020(cls):
        # -1 * rank(open-delay(high,1)) * rank(open-delay(close,1)) * rank(open-delay(low,1))
        return "Mul(-1, Mul(Mul(CSRank(Sub($open, Ref($high, 1))), CSRank(Sub($open, Ref($close, 1)))), CSRank(Sub($open, Ref($low, 1)))))"

    @classmethod
    def alpha021(cls):
        # If(sma8+std8 < sma2, -1, If(sma2 < sma8-std8, 1, If(vol/adv20>=1, 1, -1)))
        return "If(Lt(Add(Mean($close, 8), Std($close, 8)), Mean($close, 2)), -1, If(Lt(Mean($close, 2), Sub(Mean($close, 8), Std($close, 8))), 1, If(Ge(Div($volume, Mean($volume, 20)), 1), 1, -1)))"

    @classmethod
    def alpha022(cls):
        # -1 * delta(corr(high,volume,5),5) * rank(stddev(close,20))
        return "Mul(-1, Mul(Delta(Corr($high, $volume, 5), 5), CSRank(Std($close, 20))))"

    @classmethod
    def alpha023(cls):
        # If(sma(high,20) < high, -1*delta(high,2), 0)
        return "If(Lt(Mean($high, 20), $high), Mul(-1, Delta($high, 2)), 0)"

    @classmethod
    def alpha024(cls):
        # If(delta(sma(close,100),100)/delay(close,100)<=0.05, -1*(close-ts_min(close,100)), -1*delta(close,3))
        return "If(Le(Div(Delta(Mean($close, 100), 100), Ref($close, 100)), 0.05), Mul(-1, Sub($close, Ts_Min($close, 100))), Mul(-1, Delta($close, 3)))"

    @classmethod
    def alpha025(cls):
        # rank(-1 * returns * adv20 * vwap * (high-close))
        return "CSRank(Mul(Mul(Mul(Mul(-1, Sub(Div($close, Ref($close, 1)), 1)), Mean($volume, 20)), SafeDiv($amount, $volume)), Sub($high, $close)))"

    @classmethod
    def alpha026(cls):
        # -1 * ts_max(corr(Ts_Rank(volume,5), Ts_Rank(high,5), 5), 3)
        return "Mul(-1, Ts_Max(Corr(Ts_Rank($volume, 5), Ts_Rank($high, 5), 5), 3))"

    @classmethod
    def alpha027(cls):
        # If(0.5 < rank(sma(corr(rank(volume),rank(vwap),6),2)), -1, 1)
        return "If(Lt(0.5, CSRank(Mean(Corr(CSRank($volume), CSRank(SafeDiv($amount, $volume)), 6), 2))), -1, 1)"

    @classmethod
    def alpha028(cls):
        # scale(corr(adv20,low,5) + ((high+low)/2 - close))
        return "CSRank(Add(Corr(Mean($volume, 20), $low, 5), Sub(Div(Add($high, $low), 2), $close)))"

    @classmethod
    def alpha029(cls):
        # min(product(rank(rank(scale(log(sum(ts_min(rank(rank(-1*rank(delta(close,5)))),2),1))))),1),5)
        # + Ts_Rank(delay(-1*returns,6),5)
        return "Add(CSRank(Less(CSRank(CSRank(Log(Sum(Less(CSRank(CSRank(Mul(-1, CSRank(Delta($close, 5))))), 2), 1)))), 5)), Ts_Rank(Ref(Mul(-1, Sub(Div($close, Ref($close, 1)), 1)), 6), 5))"

    @classmethod
    def alpha030(cls):
        # (1-rank(sign(close-d1)+sign(d1-d2)+sign(d2-d3))) * sum(vol,5)/sum(vol,20)
        return "Mul(Sub(1.0, CSRank(Add(Add(Sign(Sub($close, Ref($close, 1))), Sign(Sub(Ref($close, 1), Ref($close, 2)))), Sign(Sub(Ref($close, 2), Ref($close, 3)))))), Div(Sum($volume, 5), Sum($volume, 20)))"

    @classmethod
    def alpha031(cls):
        # rank(wma(-1*rank(rank(delta(close,10))),10)) + rank(-1*delta(close,3)) + sign(corr(adv20,low,12))
        return "Add(Add(CSRank(WMA(Mul(-1, CSRank(CSRank(Delta($close, 10)))), 10)), CSRank(Mul(-1, Delta($close, 3)))), Sign(Corr(Mean($volume, 20), $low, 12)))"

    @classmethod
    def alpha032(cls):
        # scale((sum(close,7)/7-close)) + 20*scale(corr(vwap,delay(close,5),230))
        return "Add(CSScale(Sub(Div(Sum($close, 7), 7), $close)), Mul(20, CSScale(Corr($close, Ref($close, 5), 30))))"

    @classmethod
    def alpha033(cls):
        # rank(-1 * (1 - open/close))
        return "CSRank(Mul(-1, Sub(1, Div($open, $close))))"

    @classmethod
    def alpha034(cls):
        # rank((1-rank(std(ret,2)/std(ret,5))) + (1-rank(delta(close,1))))
        return "CSRank(Add(Sub(1, CSRank(Div(Std(Sub(Div($close, Ref($close, 1)), 1), 2), Std(Sub(Div($close, Ref($close, 1)), 1), 5)))), Sub(1, CSRank(Delta($close, 1)))))"

    @classmethod
    def alpha035(cls):
        # Ts_Rank(vol,32) * (1-Ts_Rank(close+high-low,16)) * (1-Ts_Rank(ret,32))
        return "Mul(Mul(Ts_Rank($volume, 32), Sub(1, Ts_Rank(Sub(Add($close, $high), $low), 16))), Sub(1, Ts_Rank(Sub(Div($close, Ref($close, 1)), 1), 32)))"

    @classmethod
    def alpha036(cls):
        # 2.21*rank(corr(c-o,delay(v,1),15)) + 0.7*rank(o-c) + 0.73*rank(Ts_Rank(delay(-ret,6),5))
        # + rank(abs(corr(vwap,adv20,6))) + 0.6*rank((sma(c,200)-o)*(c-o))
        return "Add(Add(Add(Add(Mul(2.21, CSRank(Corr(Sub($close, $open), Ref($volume, 1), 15))), Mul(0.7, CSRank(Sub($open, $close)))), Mul(0.73, CSRank(Ts_Rank(Ref(Mul(-1, Sub(Div($close, Ref($close, 1)), 1)), 6), 5)))), CSRank(Abs(Corr(SafeDiv($amount, $volume), Mean($volume, 20), 6)))), Mul(0.6, CSRank(Mul(Sub(Mean($close, 200), $open), Sub($close, $open)))))"

    @classmethod
    def alpha037(cls):
        # rank(corr(delay(open-close,1),close,200)) + rank(open-close)
        return "Add(CSRank(Corr(Ref(Sub($open, $close), 1), $close, 200)), CSRank(Sub($open, $close)))"

    @classmethod
    def alpha038(cls):
        # -1*rank(Ts_Rank(close,10)) * rank(close/open)
        return "Mul(Mul(-1, CSRank(Ts_Rank($close, 10))), CSRank(Div($close, $open)))"

    @classmethod
    def alpha039(cls):
        # -1*rank(delta(close,7)*(1-rank(wma(vol/adv20,9)))) * (1+rank(sum(ret,250)))
        return "Mul(Mul(-1, CSRank(Mul(Delta($close, 7), Sub(1, CSRank(WMA(Div($volume, Mean($volume, 20)), 9)))))), Add(1, CSRank(Sum(Sub(Div($close, Ref($close, 1)), 1), 250))))"

    @classmethod
    def alpha040(cls):
        # -1*rank(std(high,10)) * corr(high,volume,10)
        return "Mul(Mul(-1, CSRank(Std($high, 10))), Corr($high, $volume, 10))"

    @classmethod
    def alpha041(cls):
        # (high*low)^0.5 - vwap
        return "Sub(Pow(Mul($high, $low), 0.5), SafeDiv($amount, $volume))"

    @classmethod
    def alpha042(cls):
        # rank(vwap-close) / rank(vwap+close)
        return "Div(CSRank(Sub(SafeDiv($amount, $volume), $close)), CSRank(Add(SafeDiv($amount, $volume), $close)))"

    @classmethod
    def alpha043(cls):
        # Ts_Rank(vol/adv20,20) * Ts_Rank(-1*delta(close,7),8)
        return "Mul(Ts_Rank(Div($volume, Mean($volume, 20)), 20), Ts_Rank(Mul(-1, Delta($close, 7)), 8))"

    @classmethod
    def alpha044(cls):
        # -1 * corr(high, rank(volume), 5)
        return "Mul(-1, Corr($high, CSRank($volume), 5))"

    @classmethod
    def alpha045(cls):
        # -1 * rank(sma(delay(close,5),20)) * corr(close,vol,2) * rank(corr(sum(close,5),sum(close,20),2))
        return "Mul(-1, Mul(Mul(CSRank(Mean(Ref($close, 5), 20)), Corr($close, $volume, 2)), CSRank(Corr(Sum($close, 5), Sum($close, 20), 2))))"

    @classmethod
    def alpha046(cls):
        # If(0.25 < momentum, -1, If(momentum<0, 1, -1*(close-delay(close,1))))
        # momentum = (delay(c,20)-delay(c,10))/10 - (delay(c,10)-c)/10
        return "If(Lt(0.25, Sub(Div(Sub(Ref($close, 20), Ref($close, 10)), 10), Div(Sub(Ref($close, 10), $close), 10))), -1, If(Lt(Sub(Div(Sub(Ref($close, 20), Ref($close, 10)), 10), Div(Sub(Ref($close, 10), $close), 10)), 0), 1, Mul(-1, Sub($close, Ref($close, 1)))))"

    @classmethod
    def alpha047(cls):
        # (rank(1/close)*vol/adv20) * (high*rank(high-close)/sma(high,5)) - rank(vwap-delay(vwap,5))
        return "Sub(Mul(Div(Mul(CSRank(Div(1, $close)), $volume), Mean($volume, 20)), Div(Mul($high, CSRank(Sub($high, $close))), Mean($high, 5))), CSRank(Sub(SafeDiv($amount, $volume), Ref(SafeDiv($amount, $volume), 5))))"

    @classmethod
    def alpha048(cls):
        # IndNeutralize(...) / Sum(Pow(...),250)  — 注意：IndNeutralize 未註冊
        return "Div(IndNeutralize(Div(Mul(Corr(Delta($close, 1), Delta(Ref($close, 1), 1), 250), Delta($close, 1)), $close), $subindustry), Sum(Pow(Div(Delta($close, 1), Ref($close, 1)), 2), 250))"
        #return "Div(IndNeutralize(Div(Mul(Corr(Delta($close, 1), Delta(Ref($close, 1), 1), 250), Delta($close, 1)), $close), 0), Sum(Pow(Div(Delta($close, 1), Ref($close, 1)), 2), 250))"
    @classmethod
    def alpha049(cls):
        # If(momentum < -0.1, 1, -1*(close-delay(close,1)))
        return "If(Lt(Sub(Div(Sub(Ref($close, 20), Ref($close, 10)), 10), Div(Sub(Ref($close, 10), $close), 10)), -0.1), 1, Mul(-1, Sub($close, Ref($close, 1))))"

    @classmethod
    def alpha050(cls):
        # -1 * ts_max(rank(corr(rank(vol),rank(vwap),5)),5)
        return "Mul(-1, Ts_Max(CSRank(Corr(CSRank($volume), CSRank(SafeDiv($amount, $volume)), 5)), 5))"

    @classmethod
    def alpha051(cls):
        # (delay(c,20)-delay(c,10))/10 - (delay(c,10)-c)/10
        return "Sub(Div(Sub(Ref($close, 20), Ref($close, 10)), 10), Div(Sub(Ref($close, 10), $close), 10))"

    @classmethod
    def alpha052(cls):
        # ((-1*ts_min(low,5))+delay(ts_min(low,5),5)) * rank((sum(ret,240)-sum(ret,20))/220) * Ts_Rank(vol,5)
        return "Mul(Mul(Add(Mul(-1, Ts_Min($low, 5)), Ref(Ts_Min($low, 5), 5)), CSRank(Div(Sub(Sum(Sub(Div($close, Ref($close, 1)), 1), 240), Sum(Sub(Div($close, Ref($close, 1)), 1), 20)), 220))), Ts_Rank($volume, 5))"

    @classmethod
    def alpha053(cls):
        # -1 * delta(((close-low)-(high-close))/(high-low), 9)
        return "Mul(-1, Delta(Div(Sub(Sub($close, $low), Sub($high, $close)), Sub($high, $low)), 9))"

    @classmethod
    def alpha054(cls):
        # -1 * rank((std(abs(close-vwap),5)+(close-vwap))+corr(close,vol,6))
        return "Mul(-1, CSRank(Add(Add(Std(Abs(Sub($close, SafeDiv($amount, $volume))), 5), Sub($close, SafeDiv($amount, $volume))), Corr($close, $volume, 6))))"

    @classmethod
    def alpha055(cls):
        # -1 * corr(rank((close-ts_min(low,12))/(ts_max(high,12)-ts_min(low,12))), rank(vol), 6)
        return "Mul(-1, Corr(CSRank(Div(Sub($close, Ts_Min($low, 12)), Sub(Ts_Max($high, 12), Ts_Min($low, 12)))), CSRank($volume), 6))"

    @classmethod
    def alpha056(cls):
        # -1 * (rank(sum(ret,10)/sum(sum(ret,2),3)) * rank(ret*cap))
        return "Mul(-1, Mul(CSRank(Div(Sum(Sub(Div($close, Ref($close, 1)), 1), 10), Sum(Sum(Sub(Div($close, Ref($close, 1)), 1), 2), 3))), CSRank(Mul(Sub(Div($close, Ref($close, 1)), 1), $market_value_million))))"

    @classmethod
    def alpha057(cls):
        # -1 * ((close-vwap) / wma(rank(ts_argmax(close,30)),2))
        return "Mul(-1, Div(Sub($close, SafeDiv($amount, $volume)), WMA(CSRank(Ts_ArgMax($close, 30)), 2)))"

    @classmethod
    def alpha058(cls):
        # -1 * Ts_Rank(wma(corr(IndNeutralize(vwap,ind),vol,4),8),6) — IndNeutralize 未註冊
        return "Mul(-1, Ts_Rank(WMA(Corr(IndNeutralize(SafeDiv($amount, $volume), $industry), $volume, 4), 8), 6))"

    @classmethod
    def alpha059(cls):
        # -1 * Ts_Rank(wma(corr(IndNeutralize(vwap,ind),vol,4),16),8) — IndNeutralize 未註冊
        return "Mul(-1, Ts_Rank(WMA(Corr(IndNeutralize(Add(Mul(SafeDiv($amount, $volume), 0.728317), Mul(SafeDiv($amount, $volume), 0.271683)), $industry), $volume, 4), 16), 8))"

    @classmethod
    def alpha060(cls):
        # 0-(1*((2*scale(rank(((c-l)-(h-c))/(h-l)*vol)))-scale(rank(ts_argmax(c,10)))))
        # 注意：CSScale 未註冊
        return "Sub(0, Mul(1, Sub(Mul(2, CSScale(CSRank(Mul(Div(Sub(Sub($close, $low), Sub($high, $close)), Sub($high, $low)), $volume)))), CSScale(CSRank(Ts_ArgMax($close, 10))))))"

    @classmethod
    def alpha061(cls):
        # rank(vwap-ts_min(vwap,16)) < rank(corr(vwap,adv180,18))
        return "Lt(CSRank(Sub(SafeDiv($amount, $volume), Min(SafeDiv($amount, $volume), 16))), CSRank(Corr(SafeDiv($amount, $volume), Mean($amount, 180), 18)))"

    @classmethod
    def alpha062(cls):
        # (rank(corr(vwap,sum(adv20,22),10)) < rank((rank(o)+rank(o))<(rank((h+l)/2)+rank(h)))) * -1
        return "Mul(Lt(CSRank(Corr(SafeDiv($amount, $volume), Sum(Mean($amount, 20), 22), 10)), CSRank(Lt(Add(CSRank($open), CSRank($open)), Add(CSRank(Div(Add($high, $low), 2)), CSRank($high))))), -1)"

    @classmethod
    def alpha063(cls):
        # 類似 alpha062 的結構
        return "Mul(Lt(CSRank(Corr(SafeDiv($amount, $volume), Sum(Mean($amount, 20), 22), 10)), CSRank(Gt(Add(CSRank($open), CSRank($open)), Add(CSRank(Div(Add($high, $low), 2)), CSRank($high))))), -1)"

    @classmethod
    def alpha064(cls):
        # (rank(corr(sum(o*0.178+l*0.822,13),sum(adv120,13),17)) < rank(delta((h+l)/2*0.178+vwap*0.822,4))) * -1
        return "Mul(Lt(CSRank(Corr(Sum(Add(Mul($open, 0.178404), Mul($low, 0.821596)), 13), Sum(Mean($amount, 120), 13), 17)), CSRank(Delta(Add(Mul(Div(Add($high, $low), 2), 0.178404), Mul(SafeDiv($amount, $volume), 0.821596)), 4))), -1)"

    @classmethod
    def alpha065(cls):
        # (rank(corr(o*0.008+vwap*0.992,sum(adv60,9),6)) < rank(o-ts_min(o,14))) * -1
        return "Mul(Lt(CSRank(Corr(Add(Mul($open, 0.00817205), Mul(SafeDiv($amount, $volume), 0.99182795)), Sum(Mean($amount, 60), 9), 6)), CSRank(Sub($open, Ts_Min($open, 14)))), -1)"

    @classmethod
    def alpha066(cls):
        # (rank(wma(delta(vwap,4),7)) + Ts_Rank(wma((low-vwap)/(open-(h+l)/2),11),7)) * -1
        return "Mul(Add(CSRank(WMA(Delta(SafeDiv($amount, $volume), 4), 7)), Ts_Rank(WMA(Div(Sub($low, SafeDiv($amount, $volume)), Sub($open, Div(Add($high, $low), 2))), 11), 7)), -1)"

    @classmethod
    def alpha067(cls):
        # rank(h-ts_min(h,2))^rank(corr(IndNeutralize(vwap,ind),IndNeutralize(adv20,subind),6)) * -1
        # 注意：IndNeutralize 未註冊
        return "Mul(Pow(CSRank(Sub($high, Ts_Min($high, 2))), CSRank(Corr(IndNeutralize(SafeDiv($amount, $volume), $industry), IndNeutralize(Mean($amount, 20), $industry), 6))), -1)"

    @classmethod
    def alpha068(cls):
        # (Ts_Rank(corr(rank(h),rank(adv15),9),14) < rank(delta(c*0.518+l*0.482,1))) * -1
        return "Mul(Lt(Ts_Rank(Corr(CSRank($high), CSRank(Mean($amount, 15)), 9), 14), CSRank(Delta(Add(Mul($close, 0.518371), Mul($low, 0.481629)), 1))), -1)"

    @classmethod
    def alpha069(cls):
        # rank(max(delta(IndNeutralize(vwap,ind),3),5))^Ts_Rank(corr(...),9) * -1
        # 注意：IndNeutralize 未註冊
        return "Mul(Pow(CSRank(Max(Delta(IndNeutralize(SafeDiv($amount, $volume), $industry), 3), 5)), Ts_Rank(Corr(Add(Mul($close, 0.490655), Mul(SafeDiv($amount, $volume), 0.509345)), Mean($amount, 20), 5), 9)), -1)"

    @classmethod
    def alpha070(cls):
        # rank(delta(vwap,1))^Ts_Rank(corr(IndNeutralize(close,ind),adv50,18),18) * -1
        # 注意：IndNeutralize 未註冊
        return "Mul(Pow(CSRank(Delta(SafeDiv($amount, $volume), 1)), Ts_Rank(Corr(IndNeutralize($close, $industry), Mean($amount, 50), 18), 18)), -1)"

    @classmethod
    def alpha071(cls):
        # max(Ts_Rank(wma(corr(Ts_Rank(c,3),Ts_Rank(adv180,12),18),4),16),
        #     Ts_Rank(wma(rank(low+open-2*vwap)^2,16),4))
        return "Greater(Ts_Rank(WMA(Corr(Ts_Rank($close, 3), Ts_Rank(Mean($amount, 180), 12), 18), 4), 16), Ts_Rank(WMA(Pow(CSRank(Sub(Add($low, $open), Mul(2, SafeDiv($amount, $volume)))), 2), 16), 4))"

    @classmethod
    def alpha072(cls):
        # rank(wma(corr((h+l)/2,adv40,9),10)) / rank(wma(corr(Ts_Rank(vwap,4),Ts_Rank(vol,19),7),3))
        return "Div(CSRank(WMA(Corr(Div(Add($high, $low), 2), Mean($amount, 40), 9), 10)), CSRank(WMA(Corr(Ts_Rank(SafeDiv($amount, $volume), 4), Ts_Rank($volume, 19), 7), 3)))"

    @classmethod
    def alpha073(cls):
        # max(rank(wma(delta(vwap,5),3)), Ts_Rank(wma((delta(o*0.147+l*0.853,2)/(o*0.147+l*0.853))*-1,3),17)) * -1
        return "Mul(Greater(CSRank(WMA(Delta(SafeDiv($amount, $volume), 5), 3)), Ts_Rank(WMA(Mul(Div(Delta(Add(Mul($open, 0.147155), Mul($low, 0.852845)), 2), Add(Mul($open, 0.147155), Mul($low, 0.852845))), -1), 3), 17)), -1)"

    @classmethod
    def alpha074(cls):
        # (rank(corr(c,sum(adv30,37),15)) < rank(corr(rank(h*0.026+vwap*0.974),rank(vol),11))) * -1
        return "Mul(Lt(CSRank(Corr($close, Sum(Mean($amount, 30), 37), 15)), CSRank(Corr(CSRank(Add(Mul($high, 0.0261661), Mul(SafeDiv($amount, $volume), 0.9738339))), CSRank($volume), 11))), -1)"

    @classmethod
    def alpha075(cls):
        # rank(corr(vwap,vol,4)) < rank(corr(rank(low),rank(adv50),12))
        return "Lt(CSRank(Corr(SafeDiv($amount, $volume), $volume, 4)), CSRank(Corr(CSRank($low), CSRank(Mean($amount, 50)), 12)))"

    @classmethod
    def alpha076(cls):
        # max(rank(wma(delta(vwap,1),12)), Ts_Rank(wma(Ts_Rank(corr(IndNeutralize(low,ind),adv81,8),20),17),19)) * -1
        # 注意：IndNeutralize 未註冊
        return "Mul(Greater(CSRank(WMA(Delta(SafeDiv($amount, $volume), 1), 12)), Ts_Rank(WMA(Ts_Rank(Corr(IndNeutralize($low, $industry), Mean($amount, 81), 8), 20), 17), 19)), -1)"

    @classmethod
    def alpha077(cls):
        # min(rank(wma(((h+l)/2+h)-(vwap+h),20)), rank(wma(corr((h+l)/2,adv40,3),6)))
        return "Less(CSRank(WMA(Sub(Add(Div(Add($high, $low), 2), $high), Add(SafeDiv($amount, $volume), $high)), 20)), CSRank(WMA(Corr(Div(Add($high, $low), 2), Mean($amount, 40), 3), 6)))"

    @classmethod
    def alpha078(cls):
        # rank(corr(sum(low*0.352+vwap*0.648,20),sum(adv40,20),7)) ^ rank(corr(rank(vwap),rank(vol),6))
        return "Pow(CSRank(Corr(Sum(Add(Mul($low, 0.352233), Mul(SafeDiv($amount, $volume), 0.647767)), 20), Sum(Mean($amount, 40), 20), 7)), CSRank(Corr(CSRank(SafeDiv($amount, $volume)), CSRank($volume), 6)))"

    @classmethod
    def alpha079(cls):
        # rank(delta(IndNeutralize(c*0.607+o*0.393,ind),1)) < rank(corr(Ts_Rank(vwap,4),Ts_Rank(adv150,9),15))
        # 注意：IndNeutralize 未註冊
        return "Lt(CSRank(Delta(IndNeutralize(Add(Mul($close, 0.60733), Mul($open, 0.39267)), $industry), 1)), CSRank(Corr(Ts_Rank(SafeDiv($amount, $volume), 4), Ts_Rank(Mean($amount, 150), 9), 15)))"

    @classmethod
    def alpha080(cls):
        # (rank(sign(delta(IndNeutralize(o*0.868+h*0.132,ind),4)))^Ts_Rank(corr(h,adv10,5),6)) * -1
        # 注意：IndNeutralize 未註冊
        return "Mul(Pow(CSRank(Sign(Delta(IndNeutralize(Add(Mul($open, 0.868128), Mul($high, 0.131872)), $industry), 4))), Ts_Rank(Corr($high, Mean($amount, 10), 5), 6)), -1)"

    @classmethod
    def alpha081(cls):
        # (rank(log(prod(rank(rank(corr(vwap,sum(adv10,50),8))^4),15))) < rank(corr(rank(vwap),rank(vol),5))) * -1
        # 注意：Prod 未註冊
        return "Mul(Lt(CSRank(Log(Prod(CSRank(Pow(CSRank(Corr(SafeDiv($amount, $volume), Sum(Mean($amount, 10), 50), 8)), 4)), 15))), CSRank(Corr(CSRank(SafeDiv($amount, $volume)), CSRank($volume), 5))), -1)"

    @classmethod
    def alpha082(cls):
        # min(rank(wma(delta(open,1),15)), Ts_Rank(wma(corr(IndNeutralize(vol,ind),open,17),7),13)) * -1
        # 注意：IndNeutralize 未註冊
        return "Mul(Less(CSRank(WMA(Delta($open, 1), 15)), Ts_Rank(WMA(Corr(IndNeutralize($volume, $industry), $open, 17), 7), 13)), -1)"

    @classmethod
    def alpha083(cls):
        # (rank(delay((h-l)/(sum(c,5)/5),2))*rank(rank(vol))) / (((h-l)/(sum(c,5)/5))/(vwap-c))
        return "Div(Mul(CSRank(Ref(Div(Sub($high, $low), Div(Sum($close, 5), 5)), 2)), CSRank(CSRank($volume))), Div(Div(Sub($high, $low), Div(Sum($close, 5), 5)), Sub(SafeDiv($amount, $volume), $close)))"

    @classmethod
    def alpha084(cls):
        # SignedPower(Ts_Rank(vwap-ts_max(vwap,15),21), delta(close,5))
        return "SignedPower(Ts_Rank(Sub(SafeDiv($amount, $volume), Ts_Max(SafeDiv($amount, $volume), 15)), 21), Delta($close, 5))"

    @classmethod
    def alpha085(cls):
        # rank(corr(h*0.877+c*0.123,adv30,10)) ^ rank(corr(Ts_Rank((h+l)/2,4),Ts_Rank(vol,10),7))
        return "Pow(CSRank(Corr(Add(Mul($high, 0.876703), Mul($close, 0.123297)), Mean($amount, 30), 10)), CSRank(Corr(Ts_Rank(Div(Add($high, $low), 2), 4), Ts_Rank($volume, 10), 7)))"

    @classmethod
    def alpha086(cls):
        # (Ts_Rank(corr(close,sum(adv20,15),6),20) < rank((o+c)-(vwap+o))) * -1
        return "Mul(Lt(Ts_Rank(Corr($close, Sum(Mean($amount, 20), 15), 6), 20), CSRank(Sub(Add($open, $close), Add(SafeDiv($amount, $volume), $open)))), -1)"

    @classmethod
    def alpha087(cls):
        # max(rank(wma(delta(c*0.37+vwap*0.63,2),3)), Ts_Rank(wma(abs(corr(IndNeutralize(adv81,ind),c,13)),5),15)) * -1
        # 注意：IndNeutralize 未註冊
        return "Mul(Greater(CSRank(WMA(Delta(Add(Mul($close, 0.369701), Mul(SafeDiv($amount, $volume), 0.630299)), 2), 3)), Ts_Rank(WMA(Abs(Corr(IndNeutralize(Mean($amount, 81), $industry), $close, 13)), 5), 15)), -1)"

    @classmethod
    def alpha088(cls):
        # min(rank(wma(rank(o)+rank(l)-(rank(h)+rank(c)),8)), Ts_Rank(wma(corr(Ts_Rank(c,8),Ts_Rank(adv60,21),8),7),3))
        return "Less(CSRank(WMA(Sub(Add(CSRank($open), CSRank($low)), Add(CSRank($high), CSRank($close))), 8)), Ts_Rank(WMA(Corr(Ts_Rank($close, 8), Ts_Rank(Mean($volume, 60), 21), 8), 7), 3))"

    @classmethod
    def alpha089(cls):
        # Ts_Rank(wma(corr(low,adv10,7),6),4) - Ts_Rank(wma(delta(IndNeutralize(vwap,ind),3),10),15)
        # 注意：IndNeutralize 未註冊
        return "Sub(Ts_Rank(WMA(Corr($low, Mean($volume, 10), 7), 6), 4), Ts_Rank(WMA(Delta(IndNeutralize(SafeDiv($amount, $volume), $industry), 3), 10), 15))"

    @classmethod
    def alpha090(cls):
        # -1 * rank(close-ts_max(close,5))^Ts_Rank(corr(IndNeutralize(adv40,subind),low,5),3)
        # 注意：IndNeutralize 未註冊
        return "Mul(-1, Pow(CSRank(Sub($close, Greater($close, 5))), Ts_Rank(Corr(IndNeutralize(Mean($volume, 40), $industry), $low, 5), 3)))"

    @classmethod
    def alpha091(cls):
        # -1*(Ts_Rank(wma(wma(corr(IndNeutralize(c,ind),vol,10),16),4),5) - rank(wma(corr(vwap,adv30,4),3)))
        # 注意：IndNeutralize 未註冊
        return "Mul(-1, Sub(Ts_Rank(WMA(WMA(Corr(IndNeutralize($close, $industry), $volume, 10), 16), 4), 5), CSRank(WMA(Corr(SafeDiv($amount, $volume), Mean($volume, 30), 4), 3))))"

    @classmethod
    def alpha092(cls):
        # min(Ts_Rank(wma(If((h+l)/2+c < l+o,1,0),15),19), Ts_Rank(wma(corr(rank(l),rank(adv30),8),7),7))
        return "Less(Ts_Rank(WMA(If(Lt(Add(Div(Add($high, $low), 2), $close), Add($low, $open)), 1, 0), 15), 19), Ts_Rank(WMA(Corr(CSRank($low), CSRank(Mean($volume, 30)), 8), 7), 7))"

    @classmethod
    def alpha093(cls):
        # Ts_Rank(wma(corr(IndNeutralize(vwap,ind),adv81,17),20),8) / rank(wma(delta(0.524*c+0.476*vwap,3),16))
        # 注意：IndNeutralize 未註冊
        return "Div(Ts_Rank(WMA(Corr(IndNeutralize(SafeDiv($amount, $volume), $industry), Mean($volume, 81), 17), 20), 8), CSRank(WMA(Delta(Add(Mul(0.524, $close), Mul(0.476, SafeDiv($amount, $volume))), 3), 16)))"

    @classmethod
    def alpha094(cls):
        # -1 * rank(vwap-ts_min(vwap,12))^Ts_Rank(corr(Ts_Rank(vwap,20),Ts_Rank(adv60,4),18),3)
        return "Mul(-1, Pow(CSRank(Sub(SafeDiv($amount, $volume), Less(SafeDiv($amount, $volume), 12))), Ts_Rank(Corr(Ts_Rank(SafeDiv($amount, $volume), 20), Ts_Rank(Mean($volume, 60), 4), 18), 3)))"

    @classmethod
    def alpha095(cls):
        # If(rank(o-ts_min(o,12)) < Ts_Rank(rank(corr(sum((h+l)/2,19),sum(adv40,19),13))^5,12), 1, -1)
        return "If(Lt(CSRank(Sub($open, Less($open, 12))), Ts_Rank(Pow(CSRank(Corr(Sum(Div(Add($high, $low), 2), 19), Sum(Mean($volume, 40), 19), 13)), 5), 12)), 1, -1)"

    @classmethod
    def alpha096(cls):
        # -1*max(Ts_Rank(wma(corr(rank(vwap),rank(vol),4),4),8), Ts_Rank(wma(ts_argmax(corr(Ts_Rank(c,7),Ts_Rank(adv60,4),4),13),14),13))
        return "Mul(-1, Greater(Ts_Rank(WMA(Corr(CSRank(SafeDiv($amount, $volume)), CSRank($volume), 4), 4), 8), Ts_Rank(WMA(Ts_ArgMax(Corr(Ts_Rank($close, 7), Ts_Rank(Mean($volume, 60), 4), 4), 13), 14), 13)))"

    @classmethod
    def alpha097(cls):
        # -1*(rank(wma(delta(IndNeutralize(0.721*l+0.279*vwap,ind),3),20)) - Ts_Rank(wma(Ts_Rank(corr(Ts_Rank(l,8),Ts_Rank(adv60,17),5),19),16),7))
        # 注意：IndNeutralize 未註冊
        return "Mul(-1, Sub(CSRank(WMA(Delta(IndNeutralize(Add(Mul(0.721, $low), Mul(0.279, SafeDiv($amount, $volume))), $industry), 3), 20)), Ts_Rank(WMA(Ts_Rank(Corr(Ts_Rank($low, 8), Ts_Rank(Mean($volume, 60), 17), 5), 19), 16), 7)))"

    @classmethod
    def alpha098(cls):
        # rank(wma(corr(vwap,sum(adv5,26),5),7)) - rank(wma(Ts_Rank(ts_argmin(corr(rank(o),rank(adv15),21),9),7),8))
        return "Sub(CSRank(WMA(Corr(SafeDiv($amount, $volume), Sum(Mean($volume, 5), 26), 5), 7)), CSRank(WMA(Ts_Rank(Ts_ArgMin(Corr(CSRank($open), CSRank(Mean($volume, 15)), 21), 9), 7), 8)))"

    @classmethod
    def alpha099(cls):
        # -1*If(rank(corr(sum((h+l)/2,20),sum(adv60,20),9)) < rank(corr(low,vol,6)), 1, -1)
        return "Mul(-1, If(Lt(CSRank(Corr(Sum(Div(Add($high, $low), 2), 20), Sum(Mean($volume, 60), 20), 9)), CSRank(Corr($low, $volume, 6))), 1, -1))"

    @classmethod
    def alpha100(cls):
        # -1*(1.5*rank(IndNeutralize(rank(((c-l)-(h-c))/(h-l)*vol),subind)) - rank(IndNeutralize(corr(c,rank(adv20),5)-rank(ts_argmin(c,30)),subind))) * (vol/adv20)
        # 注意：IndNeutralize 未註冊
        return "Mul(Mul(-1, Sub(Mul(1.5, CSRank(IndNeutralize(CSRank(Mul(Div(Sub(Sub($close, $low), Sub($high, $close)), Sub($high, $low)), $volume)), $industry))), CSRank(IndNeutralize(Sub(Corr($close, CSRank(Mean($volume, 20)), 5), CSRank(Ts_ArgMin($close, 30))), $industry)))), Div($volume, Mean($volume, 20)))"

    @classmethod
    def alpha101(cls):
        # (close - open) / ((high - low) + 0.001)
        return "Div(Sub($close, $open), Add(Sub($high, $low), 0.001))"

    @classmethod
    def get_all_factors(cls):
        """一次獲取所有因子名與表達式"""
        return {name: getattr(cls, name)() for name in dir(cls) if name.startswith("alpha")}
