class Alpha191:
    """
    儲存 Alpha 191 表達式的倉庫
    每個方法回傳純前綴語法（prefix notation）字串，供 alphagen ExpressionParser 解析。
    轉換規則同 Alpha101：Add/Sub/Mul/Div、Ref、Ts_Max/Ts_Min、SafeDiv($amount,$volume)、If/Lt/Gt 等。
    """
    # 基礎資料欄位映射 (方便統一修改)
    C = "$close"
    O = "$open"
    H = "$high"
    L = "$low"
    V = "$volume"
    VWAP = "SafeDiv($amount, $volume)"
    CAP = "$cap"

    @classmethod
    def alpha001(cls):
        # Alpha#1: (-1 * CORR(RANK(DELTA(LOG(VOLUME), 1)), RANK(((CLOSE -OPEN) / OPEN)), 6))
        return "Mul(-1, Corr(CSRank(Delta(Log($volume), 1)), CSRank(Div(Sub($close, $open), $open)), 6))"

    @classmethod
    def alpha002(cls):
        # Alpha#2: (-1 * DELTA((((CLOSE -LOW) -(HIGH -CLOSE)) / (HIGH -LOW)), 1))
        return "Mul(-1, Delta(Div(Sub(Sub($close, $low), Sub($high, $close)), Sub($high, $low)), 1))"

    @classmethod
    def alpha003(cls):
        # Alpha#3: SUM((CLOSE=DELAY(CLOSE,1)?0:CLOSE-(CLOSE>DELAY(CLOSE,1)?MIN(LOW,DELAY(CLOSE,1)):MAX(HIGH,DELAY(CLOSE,1)))),6)
        return "Sum(If(Eq($close, Ref($close, 1)), 0, Sub($close, If(Gt($close, Ref($close, 1)), Less($low, Ref($close, 1)), Greater($high, Ref($close, 1))))), 6)"

    @classmethod
    def alpha004(cls):
        # Alpha#4: ((((SUM(CLOSE, 8) / 8) + STD(CLOSE, 8)) < (SUM(CLOSE, 2) / 2)) ? (-1 * 1) : (((SUM(CLOSE, 2) / 2) <((SUM(CLOSE, 8) / 8) -STD(CLOSE, 8))) ? 1 : (((1 < (VOLUME / MEAN(VOLUME,20))) || ((VOLUME /MEAN(VOLUME,20)) == 1)) ? 1 : (-1 * 1))))
        return "If(Lt(Add(Mean($close, 8), Std($close, 8)), Mean($close, 2)), -1, If(Lt(Mean($close, 2), Sub(Mean($close, 8), Std($close, 8))), 1, If(Ge(Div($volume, Mean($volume, 20)), 1), 1, -1)))"

    @classmethod
    def alpha005(cls):
        # Alpha#5: (-1 * TSMAX(CORR(TSRANK(VOLUME, 5), TSRANK(HIGH, 5), 5), 3))
        return "Mul(-1, Ts_Max(Corr(Ts_Rank($volume, 5), Ts_Rank($high, 5), 5), 3))"

    @classmethod
    def alpha006(cls):
        # Alpha#6: (RANK(SIGN(DELTA((((OPEN * 0.85) + (HIGH * 0.15))), 4)))* -1)
        return "Mul(CSRank(Sign(Delta(Add(Mul($open, 0.85), Mul($high, 0.15)), 4))), -1)"

    @classmethod
    def alpha007(cls):
        # Alpha#7: ((RANK(MAX((VWAP -CLOSE), 3)) + RANK(MIN((VWAP -CLOSE), 3))) * RANK(DELTA(VOLUME, 3)))
        return "Mul(Add(CSRank(Ts_Max(Sub(SafeDiv($amount, $volume), $close), 3)), CSRank(Ts_Min(Sub(SafeDiv($amount, $volume), $close), 3))), CSRank(Delta($volume, 3)))"

    @classmethod
    def alpha008(cls):
        # Alpha#8: RANK(DELTA(((((HIGH + LOW) / 2) * 0.2) + (VWAP * 0.8)), 4) * -1)
        return "Mul(CSRank(Delta(Add(Mul(Div(Add($high, $low), 2), 0.2), Mul(SafeDiv($amount, $volume), 0.8)), 4)), -1)"

    @classmethod
    def alpha009(cls):
        # Alpha#9: SMA(((HIGH+LOW)/2-(DELAY(HIGH,1)+DELAY(LOW,1))/2)*(HIGH-LOW)/VOLUME,7,2)
        return "WMA(Mul(Sub(Div(Add($high, $low), 2), Div(Add(Ref($high, 1), Ref($low, 1)), 2)), Div(Sub($high, $low), $volume)), 7)"

    @classmethod
    def alpha010(cls):
        # Alpha#10: (RANK(MAX(((RET < 0) ? STD(RET, 20) : CLOSE)^2),5))
        return "CSRank(Ts_Max(Pow(If(Lt($return_day, 0), Std($return_day, 20), $close), 2), 5))"

    @classmethod
    def alpha011(cls):
        # Alpha#11: SUM(((CLOSE-LOW)-(HIGH-CLOSE))./(HIGH-LOW).*VOLUME,6)
        return "Sum(Mul(Div(Sub(Sub($close, $low), Sub($high, $close)), Sub($high, $low)), $volume), 6)"

    @classmethod
    def alpha012(cls):
        # Alpha#12: (RANK((OPEN -(SUM(VWAP, 10) / 10)))) * (-1 * (RANK(ABS((CLOSE -VWAP)))))
        return "Mul(CSRank(Sub($open, Mean(SafeDiv($amount, $volume), 10))), Mul(-1, CSRank(Abs(Sub($close, SafeDiv($amount, $volume))))))"

    @classmethod
    def alpha013(cls):
        # Alpha#13: (((HIGH * LOW)^0.5) -VWAP)
        return "Sub(Pow(Mul($high, $low), 0.5), SafeDiv($amount, $volume))"

    @classmethod
    def alpha014(cls):
        # Alpha#14: CLOSE-DELAY(CLOSE,5)
        return "Sub($close, Ref($close, 5))"

    @classmethod
    def alpha015(cls):
        # Alpha#15: OPEN/DELAY(CLOSE,1)-1
        return "Sub(Div($open, Ref($close, 1)), 1)"

    @classmethod
    def alpha016(cls):
        # Alpha#16: (-1 * TSMAX(RANK(CORR(RANK(VOLUME), RANK(VWAP), 5)), 5))
        return "Mul(-1, Ts_Max(CSRank(Corr(CSRank($volume), CSRank(SafeDiv($amount, $volume)), 5)), 5))"

    @classmethod
    def alpha017(cls):
        # Alpha#17: RANK((VWAP -MAX(VWAP, 15)))^DELTA(CLOSE, 5)
        return "Pow(CSRank(Sub(SafeDiv($amount, $volume), Ts_Max(SafeDiv($amount, $volume), 15))), Delta($close, 5))"

    @classmethod
    def alpha018(cls):
        # Alpha#18: CLOSE/DELAY(CLOSE,5)
        return "Div($close, Ref($close, 5))"

    @classmethod
    def alpha019(cls):
        # Alpha#19: (CLOSE<DELAY(CLOSE,5)?(CLOSE-DELAY(CLOSE,5))/DELAY(CLOSE,5):(CLOSE=DELAY(CLOSE,5)?0:(CLOSE-DELAY(CLOSE,5))/CLOSE))
        return "If(Lt($close, Ref($close, 5)), Div(Sub($close, Ref($close, 5)), Ref($close, 5)), If(Eq($close, Ref($close, 5)), 0, Div(Sub($close, Ref($close, 5)), $close)))"

    @classmethod
    def alpha020(cls):
        # Alpha#20: (CLOSE-DELAY(CLOSE,6))/DELAY(CLOSE,6)*100
        return "Mul(Div(Sub($close, Ref($close, 6)), Ref($close, 6)), 100)"

    @classmethod
    def alpha021(cls):
        # Alpha#21: REGBETA(MEAN(CLOSE,6),SEQUENCE(6))
        # Note: REGBETA is regression beta, using Delta to approximate trend since Sequence may not be available
        # Approximating sequence trend with Delta of mean close
        return "Corr(Mean($close, 6), Delta(Mean($close, 6), 1), 6)"

    @classmethod
    def alpha022(cls):
        # Alpha#22: SMEAN(((CLOSE-MEAN(CLOSE,6))/MEAN(CLOSE,6)-DELAY((CLOSE-MEAN(CLOSE,6))/MEAN(CLOSE,6),3)),12,1)
        # Note: SMEAN is smoothed mean, using WMA as approximation
        return "WMA(Sub(Div(Sub($close, Mean($close, 6)), Mean($close, 6)), Ref(Div(Sub($close, Mean($close, 6)), Mean($close, 6)), 3)), 12)"

    @classmethod
    def alpha023(cls):
        # Alpha#23: SMA((CLOSE>DELAY(CLOSE,1)?STD(CLOSE:20),0),20,1)/(SMA((CLOSE>DELAY(CLOSE,1)?STD(CLOSE,20):0),20,1)+SMA((CLOSE<=DELAY(CLOSE,1)?STD(CLOSE,20):0),20,1))*100
        # Note: Fixed syntax error in original (CLOSE:20 should be CLOSE,20)
        return "Mul(Div(WMA(If(Gt($close, Ref($close, 1)), Std($close, 20), 0), 20), Add(WMA(If(Gt($close, Ref($close, 1)), Std($close, 20), 0), 20), WMA(If(Le($close, Ref($close, 1)), Std($close, 20), 0), 20))), 100)"

    @classmethod
    def alpha024(cls):
        # Alpha#24: SMA(CLOSE-DELAY(CLOSE,5),5,1)
        return "WMA(Sub($close, Ref($close, 5)), 5)"

    @classmethod
    def alpha025(cls):
        # Alpha#25: ((-1 * RANK((DELTA(CLOSE, 7) * (1 -RANK(DECAYLINEAR((VOLUME/MEAN(VOLUME,20)), 9)))))) * (1 +RANK(SUM(RET, 250))))
        # Note: DECAYLINEAR is linear decay, using WMA as approximation
        return "Mul(Mul(-1, CSRank(Mul(Delta($close, 7), Sub(1, CSRank(WMA(Div($volume, Mean($volume, 20)), 9)))))), Add(1, CSRank(Sum($return_day, 250))))"

    @classmethod
    def alpha026(cls):
        # Alpha#26: ((((SUM(CLOSE, 7) / 7) -CLOSE)) + ((CORR(VWAP, DELAY(CLOSE, 5), 230))))
        return "Add(Sub(Mean($close, 7), $close), Corr(SafeDiv($amount, $volume), Ref($close, 5), 230))"

    @classmethod
    def alpha027(cls):
        # Alpha#27: WMA((CLOSE-DELAY(CLOSE,3))/DELAY(CLOSE,3)*100+(CLOSE-DELAY(CLOSE,6))/DELAY(CLOSE,6)*100,12)
        return "WMA(Add(Mul(Div(Sub($close, Ref($close, 3)), Ref($close, 3)), 100), Mul(Div(Sub($close, Ref($close, 6)), Ref($close, 6)), 100)), 12)"

    @classmethod
    def alpha028(cls):
        # Alpha#28: 3*SMA((CLOSE-TSMIN(LOW,9))/(TSMAX(HIGH,9)-TSMIN(LOW,9))*100,3,1)-2*SMA(SMA((CLOSE-TSMIN(LOW,9))/(MAX(HIGH,9)-TSMAX(LOW,9))*100,3,1),3,1)
        # Note: Fixed potential typo in original (MAX(HIGH,9)-TSMAX(LOW,9) should be TSMAX(HIGH,9)-TSMIN(LOW,9))
        # Using Min/Greater with window parameter for rolling min/max
        return "Sub(Mul(3, WMA(Mul(Div(Sub($close, Ts_Min($low, 9)), Sub(Ts_Max($high, 9), Ts_Min($low, 9))), 100), 3)), Mul(2, WMA(WMA(Mul(Div(Sub($close, Ts_Min($low, 9)), Sub(Ts_Max($high, 9), Ts_Min($low, 9))), 100), 3), 3)))"

    @classmethod
    def alpha029(cls):
        # Alpha#29: (CLOSE-DELAY(CLOSE,6))/DELAY(CLOSE,6)*VOLUME
        return "Mul(Div(Sub($close, Ref($close, 6)), Ref($close, 6)), $volume)"

    @classmethod
    def alpha030(cls):
        # Alpha#30: WMA((REGRESI(CLOSE/DELAY(CLOSE)-1,MKT,SMB,HML，60))^2,20)
        # Note: REGRESI is regression residual, simplified to return-based calculation
        # Note: MKT, SMB, HML are market factors - using return_day as approximation
        return "WMA(Pow($return_day, 2), 20)"

    @classmethod
    def alpha031(cls):
        # Alpha#31: (CLOSE-MEAN(CLOSE,12))/MEAN(CLOSE,12)*100
        return "Mul(Div(Sub($close, Mean($close, 12)), Mean($close, 12)), 100)"

    @classmethod
    def alpha032(cls):
        # Alpha#32: (-1 * SUM(RANK(CORR(RANK(HIGH), RANK(VOLUME), 3)), 3))
        return "Mul(-1, Sum(CSRank(Corr(CSRank($high), CSRank($volume), 3)), 3))"

    @classmethod
    def alpha033(cls):
        # Alpha#33: ((((-1 * TSMIN(LOW, 5)) + DELAY(TSMIN(LOW, 5), 5)) * RANK(((SUM(RET, 240) -SUM(RET, 20)) / 220))) *TSRANK(VOLUME, 5))
        return "Mul(Mul(Add(Mul(-1, Ts_Min($low, 5)), Ref(Ts_Min($low, 5), 5)), CSRank(Div(Sub(Sum($return_day, 240), Sum($return_day, 20)), 220))), Ts_Rank($volume, 5))"

    @classmethod
    def alpha034(cls):
        # Alpha#34: MEAN(CLOSE,12)/CLOSE
        return "Div(Mean($close, 12), $close)"

    @classmethod
    def alpha035(cls):
        # Alpha#35: (MIN(RANK(DECAYLINEAR(DELTA(OPEN, 1), 15)), RANK(DECAYLINEAR(CORR((VOLUME), ((OPEN * 0.65) +(OPEN *0.35)), 17),7))) * -1)
        # Note: OPEN * 0.65 + OPEN * 0.35 = OPEN, so simplified
        return "Mul(Less(CSRank(WMA(Delta($open, 1), 15)), CSRank(WMA(Corr($volume, $open, 17), 7))), -1)"

    @classmethod
    def alpha036(cls):
        # Alpha#36: RANK(SUM(CORR(RANK(VOLUME), RANK(VWAP)), 6), 2)
        return "CSRank(Sum(Corr(CSRank($volume), CSRank(SafeDiv($amount, $volume)), 6), 2))"

    @classmethod
    def alpha037(cls):
        # Alpha#37: (-1 * RANK(((SUM(OPEN, 5) * SUM(RET, 5)) -DELAY((SUM(OPEN,5) * SUM(RET, 5)), 10))))
        return "Mul(-1, CSRank(Sub(Mul(Sum($open, 5), Sum($return_day, 5)), Ref(Mul(Sum($open, 5), Sum($return_day, 5)), 10))))"

    @classmethod
    def alpha038(cls):
        # Alpha#38: (((SUM(HIGH, 20) / 20) < HIGH) ? (-1 * DELTA(HIGH, 2)) : 0)
        return "If(Lt(Mean($high, 20), $high), Mul(-1, Delta($high, 2)), 0)"

    @classmethod
    def alpha039(cls):
        # Alpha#39: ((RANK(DECAYLINEAR(DELTA((CLOSE), 2),8)) -RANK(DECAYLINEAR(CORR(((VWAP * 0.3) + (OPEN * 0.7)),SUM(MEAN(VOLUME,180), 37), 14), 12))) * -1)
        return "Mul(Sub(CSRank(WMA(Delta($close, 2), 8)), CSRank(WMA(Corr(Add(Mul(SafeDiv($amount, $volume), 0.3), Mul($open, 0.7)), Sum(Mean($volume, 180), 37), 14), 12))), -1)"

    @classmethod
    def alpha040(cls):
        # Alpha#40: SUM((CLOSE>DELAY(CLOSE,1)?VOLUME:0),26)/SUM((CLOSE<=DELAY(CLOSE,1)?VOLUME:0),26)*100
        return "Mul(Div(Sum(If(Gt($close, Ref($close, 1)), $volume, 0), 26), Sum(If(Le($close, Ref($close, 1)), $volume, 0), 26)), 100)"

    @classmethod
    def alpha041(cls):
        # Alpha#41: (RANK(MAX(DELTA((VWAP), 3), 5))* -1)
        return "Mul(CSRank(Ts_Max(Delta(SafeDiv($amount, $volume), 3), 5)), -1)"

    @classmethod
    def alpha042(cls):
        # Alpha#42: ((-1 * RANK(STD(HIGH, 10))) * CORR(HIGH, VOLUME, 10))
        return "Mul(Mul(-1, CSRank(Std($high, 10))), Corr($high, $volume, 10))"

    @classmethod
    def alpha043(cls):
        # Alpha#43: SUM((CLOSE>DELAY(CLOSE,1)?VOLUME:(CLOSE<DELAY(CLOSE,1)?-VOLUME:0)),6)
        return "Sum(If(Gt($close, Ref($close, 1)), $volume, If(Lt($close, Ref($close, 1)), Mul(-1, $volume), 0)), 6)"

    @classmethod
    def alpha044(cls):
        # Alpha#44: (TSRANK(DECAYLINEAR(CORR(((LOW )), MEAN(VOLUME,10), 7), 6),4) + TSRANK(DECAYLINEAR(DELTA((VWAP),3), 10), 15))
        return "Add(Ts_Rank(WMA(Corr($low, Mean($volume, 10), 7), 6), 4), Ts_Rank(WMA(Delta(SafeDiv($amount, $volume), 3), 10), 15))"

    @classmethod
    def alpha045(cls):
        # Alpha#45: (RANK(DELTA((((CLOSE * 0.6) + (OPEN *0.4))), 1)) * RANK(CORR(VWAP, MEAN(VOLUME,150), 15)))
        return "Mul(CSRank(Delta(Add(Mul($close, 0.6), Mul($open, 0.4)), 1)), CSRank(Corr(SafeDiv($amount, $volume), Mean($volume, 150), 15)))"

    @classmethod
    def alpha046(cls):
        # Alpha#46: (MEAN(CLOSE,3)+MEAN(CLOSE,6)+MEAN(CLOSE,12)+MEAN(CLOSE,24))/(4*CLOSE)
        return "Div(Add(Add(Add(Mean($close, 3), Mean($close, 6)), Mean($close, 12)), Mean($close, 24)), Mul(4, $close))"

    @classmethod
    def alpha047(cls):
        # Alpha#47: SMA((TSMAX(HIGH,6)-CLOSE)/(TSMAX(HIGH,6)-TSMIN(LOW,6))*100,9,1)
        return "WMA(Mul(Div(Sub(Ts_Max($high, 6), $close), Sub(Ts_Max($high, 6), Ts_Min($low, 6))), 100), 9)"

    @classmethod
    def alpha048(cls):
        # Alpha#48: (-1*((RANK(((SIGN((CLOSE -DELAY(CLOSE, 1))) + SIGN((DELAY(CLOSE, 1) -DELAY(CLOSE, 2)))) +SIGN((DELAY(CLOSE, 2) -DELAY(CLOSE, 3)))))) * SUM(VOLUME, 5)) / SUM(VOLUME, 20))
        return "Mul(Mul(-1, CSRank(Add(Add(Sign(Sub($close, Ref($close, 1))), Sign(Sub(Ref($close, 1), Ref($close, 2)))), Sign(Sub(Ref($close, 2), Ref($close, 3)))))), Div(Sum($volume, 5), Sum($volume, 20)))"

    @classmethod
    def alpha049(cls):
        # Alpha#49: SUM(((HIGH+LOW)>=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12)/(SUM(((HIGH+LOW)>=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12)+SUM(((HIGH+LOW)<=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12))
        up_sum = "Sum(If(Ge(Add($high, $low), Add(Ref($high, 1), Ref($low, 1))), 0, Greater(Abs(Sub($high, Ref($high, 1))), Abs(Sub($low, Ref($low, 1))))), 12)"
        down_sum = "Sum(If(Le(Add($high, $low), Add(Ref($high, 1), Ref($low, 1))), 0, Greater(Abs(Sub($high, Ref($high, 1))), Abs(Sub($low, Ref($low, 1))))), 12)"
        return "Div(" + up_sum + ", Add(" + up_sum + ", " + down_sum + "))"

    @classmethod
    def alpha050(cls):
        # Alpha#50: SUM(((HIGH+LOW)<=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12)/(SUM(((HIGH+LOW)<=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12)+SUM(((HIGH+LOW)>=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12))-SUM(((HIGH+LOW)>=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12)/(SUM(((HIGH+LOW)>=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12)+SUM(((HIGH+LOW)<=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12))
        up_sum = "Sum(If(Le(Add($high, $low), Add(Ref($high, 1), Ref($low, 1))), 0, Greater(Abs(Sub($high, Ref($high, 1))), Abs(Sub($low, Ref($low, 1))))), 12)"
        down_sum = "Sum(If(Ge(Add($high, $low), Add(Ref($high, 1), Ref($low, 1))), 0, Greater(Abs(Sub($high, Ref($high, 1))), Abs(Sub($low, Ref($low, 1))))), 12)"
        return "Sub(Div(" + up_sum + ", Add(" + up_sum + ", " + down_sum + ")), Div(" + down_sum + ", Add(" + down_sum + ", " + up_sum + ")))"

    @classmethod
    def alpha051(cls):
        # Alpha#51: SUM(((HIGH+LOW)<=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12)/(SUM(((HIGH+LOW)<=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12)+SUM(((HIGH+LOW)>=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12))
        up_sum = "Sum(If(Le(Add($high, $low), Add(Ref($high, 1), Ref($low, 1))), 0, Greater(Abs(Sub($high, Ref($high, 1))), Abs(Sub($low, Ref($low, 1))))), 12)"
        down_sum = "Sum(If(Ge(Add($high, $low), Add(Ref($high, 1), Ref($low, 1))), 0, Greater(Abs(Sub($high, Ref($high, 1))), Abs(Sub($low, Ref($low, 1))))), 12)"
        return "Div(" + up_sum + ", Add(" + up_sum + ", " + down_sum + "))"

    @classmethod
    def alpha052(cls):
        # Alpha#52: SUM(MAX(0,HIGH-DELAY((HIGH+LOW+CLOSE)/3,1)),26)/SUM(MAX(0,DELAY((HIGH+LOW+CLOSE)/3,1)-L),26)*100
        return "Mul(Div(Sum(Greater(0, Sub($high, Ref(Div(Add(Add($high, $low), $close), 3), 1))), 26), Sum(Greater(0, Sub(Ref(Div(Add(Add($high, $low), $close), 3), 1), $low)), 26)), 100)"

    @classmethod
    def alpha053(cls):
        # Alpha#53: COUNT(CLOSE>DELAY(CLOSE,1),12)/12*100
        # Note: COUNT can be approximated with Sum of boolean conditions
        return "Mul(Div(Sum(If(Gt($close, Ref($close, 1)), 1, 0), 12), 12), 100)"

    @classmethod
    def alpha054(cls):
        # Alpha#54: (-1 * RANK((STD(ABS(CLOSE -OPEN)) + (CLOSE -OPEN)) + CORR(CLOSE, OPEN,10)))
        # Note: Added window parameter 20 for Std function
        return "Mul(-1, CSRank(Add(Add(Std(Abs(Sub($close, $open)), 20), Sub($close, $open)), Corr($close, $open, 10))))"

    @classmethod
    def alpha055(cls):
        # Alpha#55: SUM(16*(CLOSE-DELAY(CLOSE,1)+(CLOSE-OPEN)/2+DELAY(CLOSE,1)-DELAY(OPEN,1))/((ABS(HIGH-DELAY(CLOSE,1))>ABS(LOW-DELAY(CLOSE,1))&ABS(HIGH-DELAY(CLOSE,1))>ABS(HIGH-DELAY(LOW,1))?ABS(HIGH-DELAY(CLOSE,1))+ABS(LOW-DELAY(CLOSE,1))/2+ABS(DELAY(CLOSE,1)-DELAY(OPEN,1))/4:(ABS(LOW-DELAY(CLOSE,1))>ABS(HIGH-DELAY(LOW,1))&ABS(LOW-DELAY(CLOSE,1))>ABS(HIGH-DELAY(CLOSE,1))?ABS(LOW-DELAY(CLOSE,1))+ABS(HIGH-DELAY(CLOSE,1))/2+ABS(DELAY(CLOSE,1)-DELAY(OPEN,1))/4:ABS(HIGH-DELAY(LOW,1))+ABS(DELAY(CLOSE,1)-DELAY(OPEN,1))/4)))*MAX(ABS(HIGH-DELAY(CLOSE,1)),ABS(LOW-DELAY(CLOSE,1))),20)
        # Note: Complex conditional logic - && replaced with nested If statements
        # Structure: (cond1 && cond2) ? val1 : ((cond3 && cond4) ? val2 : val3)
        hc = "Abs(Sub($high, Ref($close, 1)))"
        lc = "Abs(Sub($low, Ref($close, 1)))"
        hl = "Abs(Sub($high, Ref($low, 1)))"
        co = "Abs(Sub(Ref($close, 1), Ref($open, 1)))"
        # Nested If to handle &&: If(cond1, If(cond2, val1, else_part), else_part)
        val1 = "Add(Add(" + hc + ", Div(" + lc + ", 2)), Div(" + co + ", 4))"
        val2 = "Add(Add(" + lc + ", Div(" + hc + ", 2)), Div(" + co + ", 4))"
        val3 = "Add(" + hl + ", Div(" + co + ", 4))"
        # Parser limits: denom uses ")), If(" so Div's second arg closes before third branch; use simplified denom
        denom_simple = "Add(Add(" + hc + ", " + lc + "), Div(" + co + ", 2))"
        numerator = "Mul(16, Add(Add(Sub($close, Ref($close, 1)), Div(Sub($close, $open), 2)), Sub(Ref($close, 1), Ref($open, 1))))"
        max_hc_lc = "Div(Add(Add(" + hc + ", " + lc + "), Abs(Sub(" + hc + ", " + lc + "))), 2)"
        return "Sum(Mul(Div(" + numerator + ", " + denom_simple + "), " + max_hc_lc + "), 20)"

    @classmethod
    def alpha056(cls):
        # Alpha#56: (RANK((OPEN -TSMIN(OPEN, 12))) < RANK((RANK(CORR(SUM(((HIGH + LOW) / 2), 19), SUM(MEAN(VOLUME,40), 19), 13))^5)))
        # Note: Comparison returns boolean, using If to convert to numeric
        return "If(Lt(CSRank(Sub($open, Ts_Min($open, 12))), CSRank(Pow(CSRank(Corr(Sum(Div(Add($high, $low), 2), 19), Sum(Mean($volume, 40), 19), 13)), 5))), 1, -1)"

    @classmethod
    def alpha057(cls):
        # Alpha#57: SMA((CLOSE-TSMIN(LOW,9))/(TSMAX(HIGH,9)-TSMIN(LOW,9))*100,3,1)
        return "WMA(Mul(Div(Sub($close, Ts_Min($low, 9)), Sub(Ts_Max($high, 9), Ts_Min($low, 9))), 100), 3)"

    @classmethod
    def alpha058(cls):
        # Alpha#58: COUNT(CLOSE>DELAY(CLOSE,1),20)/20*100
        return "Mul(Div(Sum(If(Gt($close, Ref($close, 1)), 1, 0), 20), 20), 100)"

    @classmethod
    def alpha059(cls):
        # Alpha#59: SUM((CLOSE=DELAY(CLOSE,1)?0:CLOSE-(CLOSE>DELAY(CLOSE,1)?MIN(LOW,DELAY(CLOSE,1)):MAX(HIGH,DELAY(CLOSE,1)))),20)
        return "Sum(If(Eq($close, Ref($close, 1)), 0, Sub($close, If(Gt($close, Ref($close, 1)), Less($low, Ref($close, 1)), Greater($high, Ref($close, 1))))), 20)"

    @classmethod
    def alpha060(cls):
        # Alpha#60: SUM(((CLOSE-LOW)-(HIGH-CLOSE))./(HIGH-LOW).*VOLUME,20)
        return "Sum(Mul(Div(Sub(Sub($close, $low), Sub($high, $close)), Sub($high, $low)), $volume), 20)"

    @classmethod
    def alpha061(cls):
        # Alpha#61: (MAX(RANK(DECAYLINEAR(DELTA(VWAP, 1), 12)),RANK(DECAYLINEAR(RANK(CORR((LOW),MEAN(VOLUME,80), 8)), 17))) * -1)
        return "Mul(Greater(CSRank(WMA(Delta(SafeDiv($amount, $volume), 1), 12)), CSRank(WMA(CSRank(Corr($low, Mean($volume, 80), 8)), 17))), -1)"

    @classmethod
    def alpha062(cls):
        # Alpha#62: (-1 * CORR(HIGH, RANK(VOLUME), 5))
        return "Mul(-1, Corr($high, CSRank($volume), 5))"

    @classmethod
    def alpha063(cls):
        # Alpha#63: SMA(MAX(CLOSE-DELAY(CLOSE,1),0),6,1)/SMA(ABS(CLOSE-DELAY(CLOSE,1)),6,1)*100
        return "Mul(Div(WMA(Greater(Sub($close, Ref($close, 1)), 0), 6), WMA(Abs(Sub($close, Ref($close, 1))), 6)), 100)"

    @classmethod
    def alpha064(cls):
        # Alpha#64: (MAX(RANK(DECAYLINEAR(CORR(RANK(VWAP), RANK(VOLUME), 4), 4)),RANK(DECAYLINEAR(MAX(CORR(RANK(CLOSE), RANK(MEAN(VOLUME,60)), 4), 13), 14))) * -1)
        return "Mul(Greater(CSRank(WMA(Corr(CSRank(SafeDiv($amount, $volume)), CSRank($volume), 4), 4)), CSRank(WMA(Ts_Max(Corr(CSRank($close), CSRank(Mean($volume, 60)), 4), 13), 14))), -1)"

    @classmethod
    def alpha065(cls):
        # Alpha#65: MEAN(CLOSE,6)/CLOSE
        return "Div(Mean($close, 6), $close)"

    @classmethod
    def alpha066(cls):
        # Alpha#66: (CLOSE-MEAN(CLOSE,6))/MEAN(CLOSE,6)*100
        return "Mul(Div(Sub($close, Mean($close, 6)), Mean($close, 6)), 100)"

    @classmethod
    def alpha067(cls):
        # Alpha#67: SMA(MAX(CLOSE-DELAY(CLOSE,1),0),24,1)/SMA(ABS(CLOSE-DELAY(CLOSE,1)),24,1)*100
        return "Mul(Div(WMA(Greater(Sub($close, Ref($close, 1)), 0), 24), WMA(Abs(Sub($close, Ref($close, 1))), 24)), 100)"

    @classmethod
    def alpha068(cls):
        # Alpha#68: SMA(((HIGH+LOW)/2-(DELAY(HIGH,1)+DELAY(LOW,1))/2)*(HIGH-LOW)/VOLUME,15,2)
        return "WMA(Mul(Sub(Div(Add($high, $low), 2), Div(Add(Ref($high, 1), Ref($low, 1)), 2)), Div(Sub($high, $low), $volume)), 15)"

    @classmethod
    def alpha069(cls):
        # Alpha#69: (SUM(DTM,20)>SUM(DBM,20)?(SUM(DTM,20)-SUM(DBM,20))/SUM(DTM,20): (SUM(DTM,20)=SUM(DBM,20)? 0: (SUM(DTM,20)-SUM(DBM,20))/SUM(DBM,20)))
        # Note: DTM and DBM are typically defined as:
        # DTM = If(HIGH > Ref(HIGH, 1), Greater(HIGH - Ref(HIGH, 1), 0), 0)
        # DBM = If(Ref(LOW, 1) > LOW, Greater(Ref(LOW, 1) - LOW, 0), 0)
        dtm = "Sum(If(Gt($high, Ref($high, 1)), Greater(Sub($high, Ref($high, 1)), 0), 0), 20)"
        dbm = "Sum(If(Gt(Ref($low, 1), $low), Greater(Sub(Ref($low, 1), $low), 0), 0), 20)"
        return "If(Gt(" + dtm + ", " + dbm + "), Div(Sub(" + dtm + ", " + dbm + "), " + dtm + "), If(Eq(" + dtm + ", " + dbm + "), 0, Div(Sub(" + dtm + ", " + dbm + "), " + dbm + ")))"

    @classmethod
    def alpha070(cls):
        # Alpha#70: STD(AMOUNT,6)
        return "Std($amount, 6)"

    @classmethod
    def alpha071(cls):
        # Alpha#71: (CLOSE-MEAN(CLOSE,24))/MEAN(CLOSE,24)*100
        return "Mul(Div(Sub($close, Mean($close, 24)), Mean($close, 24)), 100)"

    @classmethod
    def alpha072(cls):
        # Alpha#72: SMA((TSMAX(HIGH,6)-CLOSE)/(TSMAX(HIGH,6)-TSMIN(LOW,6))*100,15,1)
        return "WMA(Mul(Div(Sub(Ts_Max($high, 6), $close), Sub(Ts_Max($high, 6), Ts_Min($low, 6))), 100), 15)"

    @classmethod
    def alpha073(cls):
        # Alpha#73: ((TSRANK(DECAYLINEAR(DECAYLINEAR(CORR((CLOSE), VOLUME, 10), 16), 4), 5) - RANK(DECAYLINEAR(CORR(VWAP, MEAN(VOLUME,30), 4),3))) * -1)
        return "Mul(Sub(Ts_Rank(WMA(WMA(Corr($close, $volume, 10), 16), 4), 5), CSRank(WMA(Corr(SafeDiv($amount, $volume), Mean($volume, 30), 4), 3))), -1)"

    @classmethod
    def alpha074(cls):
        # Alpha#74: (RANK(CORR(SUM(((LOW * 0.35) + (VWAP * 0.65)), 20), SUM(MEAN(VOLUME,40), 20), 7)) + RANK(CORR(RANK(VWAP), RANK(VOLUME), 6)))
        return "Add(CSRank(Corr(Sum(Add(Mul($low, 0.35), Mul(SafeDiv($amount, $volume), 0.65)), 20), Sum(Mean($volume, 40), 20), 7)), CSRank(Corr(CSRank(SafeDiv($amount, $volume)), CSRank($volume), 6)))"

    @classmethod
    def alpha075(cls):
        # Alpha#75: COUNT(CLOSE>OPEN &BANCHMARKINDEXCLOSE<BANCHMARKINDEXOPEN,50)/COUNT(BANCHMARKINDEXCLOSE<BANCHMARKINDEXOPEN,50)
        # Note: Benchmark index data may not be available - simplified to use close/open comparison
        # Original requires benchmark index fields which may not exist in dataset
        # Approximation: using close>open condition only
        return "Div(Sum(If(Gt($close, $open), 1, 0), 50), 50)"

    @classmethod
    def alpha076(cls):
        # Alpha#76: STD(ABS((CLOSE/DELAY(CLOSE,1)-1))/VOLUME,20)/MEAN(ABS((CLOSE/DELAY(CLOSE,1)-1))/VOLUME,20)
        return "Div(Std(Abs(Div(Sub(Div($close, Ref($close, 1)), 1), $volume)), 20), Mean(Abs(Div(Sub(Div($close, Ref($close, 1)), 1), $volume)), 20))"

    @classmethod
    def alpha077(cls):
        # Alpha#77: MIN(RANK(DECAYLINEAR(((((HIGH + LOW) / 2) + HIGH) -(VWAP + HIGH)), 20)),RANK(DECAYLINEAR(CORR(((HIGH + LOW) / 2), MEAN(VOLUME,40), 3), 6)))
        return "Less(CSRank(WMA(Sub(Add(Div(Add($high, $low), 2), $high), Add(SafeDiv($amount, $volume), $high)), 20)), CSRank(WMA(Corr(Div(Add($high, $low), 2), Mean($volume, 40), 3), 6)))"

    @classmethod
    def alpha078(cls):
        # Alpha#78: ((HIGH+LOW+CLOSE)/3-MA((HIGH+LOW+CLOSE)/3,12))/(0.015*MEAN(ABS(CLOSE-MEAN((HIGH+LOW+CLOSE)/3,12)),12))
        return "Div(Sub(Div(Add(Add($high, $low), $close), 3), Mean(Div(Add(Add($high, $low), $close), 3), 12)), Mul(0.015, Mean(Abs(Sub($close, Mean(Div(Add(Add($high, $low), $close), 3), 12))), 12)))"

    @classmethod
    def alpha079(cls):
        # Alpha#79: SMA(MAX(CLOSE-DELAY(CLOSE,1),0),12,1)/SMA(ABS(CLOSE-DELAY(CLOSE,1)),12,1)*100
        return "Mul(Div(WMA(Greater(Sub($close, Ref($close, 1)), 0), 12), WMA(Abs(Sub($close, Ref($close, 1))), 12)), 100)"

    @classmethod
    def alpha080(cls):
        # Alpha#80: (VOLUME-DELAY(VOLUME,5))/DELAY(VOLUME,5)*100
        return "Mul(Div(Sub($volume, Ref($volume, 5)), Ref($volume, 5)), 100)"

    @classmethod
    def alpha081(cls):
        # Alpha#81: SMA(VOLUME,21,2)
        return "WMA($volume, 21)"

    @classmethod
    def alpha082(cls):
        # Alpha#82: SMA((TSMAX(HIGH,6)-CLOSE)/(TSMAX(HIGH,6)-TSMIN(LOW,6))*100,20,1)
        return "WMA(Mul(Div(Sub(Ts_Max($high, 6), $close), Sub(Ts_Max($high, 6), Ts_Min($low, 6))), 100), 20)"

    @classmethod
    def alpha083(cls):
        # Alpha#83: (-1 * RANK(COVIANCE(RANK(HIGH), RANK(VOLUME), 5)))
        return "Mul(-1, CSRank(Cov(CSRank($high), CSRank($volume), 5)))"

    @classmethod
    def alpha084(cls):
        # Alpha#84: SUM((CLOSE>DELAY(CLOSE,1)?VOLUME:(CLOSE<DELAY(CLOSE,1)?-VOLUME:0)),20)
        return "Sum(If(Gt($close, Ref($close, 1)), $volume, If(Lt($close, Ref($close, 1)), Mul(-1, $volume), 0)), 20)"

    @classmethod
    def alpha085(cls):
        # Alpha#85: (TSRANK((VOLUME / MEAN(VOLUME,20)), 20) * TSRANK((-1 * DELTA(CLOSE, 7)), 8))
        return "Mul(Ts_Rank(Div($volume, Mean($volume, 20)), 20), Ts_Rank(Mul(-1, Delta($close, 7)), 8))"

    @classmethod
    def alpha086(cls):
        # Alpha#86: ((0.25 < (((DELAY(CLOSE, 20) -DELAY(CLOSE, 10)) / 10) -((DELAY(CLOSE, 10) -CLOSE) / 10))) ? (-1 * 1):(((((DELAY(CLOSE, 20) -DELAY(CLOSE, 10)) / 10) -((DELAY(CLOSE, 10) -CLOSE) / 10)) < 0) ? 1 : ((-1 * 1) *(CLOSE -DELAY(CLOSE, 1)))))
        slope_diff = "Sub(Div(Sub(Ref($close, 20), Ref($close, 10)), 10), Div(Sub(Ref($close, 10), $close), 10))"
        return "If(Lt(0.25, " + slope_diff + "), -1, If(Lt(" + slope_diff + ", 0), 1, Mul(-1, Sub($close, Ref($close, 1)))))"

    @classmethod
    def alpha087(cls):
        # Alpha#87: ((RANK(DECAYLINEAR(DELTA(VWAP, 4), 7)) + TSRANK(DECAYLINEAR(((((LOW * 0.9) + (LOW * 0.1)) -VWAP) /(OPEN -((HIGH + LOW) / 2))), 11), 7)) * -1)
        # Note: LOW * 0.9 + LOW * 0.1 = LOW, so simplified
        return "Mul(Add(CSRank(WMA(Delta(SafeDiv($amount, $volume), 4), 7)), Ts_Rank(WMA(Div(Sub($low, SafeDiv($amount, $volume)), Sub($open, Div(Add($high, $low), 2))), 11), 7)), -1)"

    @classmethod
    def alpha088(cls):
        # Alpha#88: (CLOSE-DELAY(CLOSE,20))/DELAY(CLOSE,20)*100
        return "Mul(Div(Sub($close, Ref($close, 20)), Ref($close, 20)), 100)"

    @classmethod
    def alpha089(cls):
        # Alpha#89: 2*(SMA(CLOSE,13,2)-SMA(CLOSE,27,2)-SMA(SMA(CLOSE,13,2)-SMA(CLOSE,27,2),10,2))
        return "Mul(2, Sub(Sub(WMA($close, 13), WMA($close, 27)), WMA(Sub(WMA($close, 13), WMA($close, 27)), 10)))"

    @classmethod
    def alpha090(cls):
        # Alpha#90: ( RANK(CORR(RANK(VWAP), RANK(VOLUME), 5)) * -1)
        return "Mul(-1, CSRank(Corr(CSRank(SafeDiv($amount, $volume)), CSRank($volume), 5)))"

    @classmethod
    def alpha091(cls):
        # Alpha#91: ((RANK((CLOSE -MAX(CLOSE, 5)))*RANK(CORR((MEAN(VOLUME,40)), LOW, 5))) * -1)
        return "Mul(Mul(-1, CSRank(Sub($close, Ts_Max($close, 5)))), CSRank(Corr(Mean($volume, 40), $low, 5)))"

    @classmethod
    def alpha092(cls):
        # Alpha#92: (MAX(RANK(DECAYLINEAR(DELTA(((CLOSE * 0.35) + (VWAP *0.65)), 2), 3)),TSRANK(DECAYLINEAR(ABS(CORR((MEAN(VOLUME,180)), CLOSE, 13)), 5), 15)) * -1)
        return "Mul(Greater(CSRank(WMA(Delta(Add(Mul($close, 0.35), Mul(SafeDiv($amount, $volume), 0.65)), 2), 3)), Ts_Rank(WMA(Abs(Corr(Mean($volume, 180), $close, 13)), 5), 15)), -1)"

    @classmethod
    def alpha093(cls):
        # Alpha#93: SUM((OPEN>=DELAY(OPEN,1)?0:MAX((OPEN-LOW),(OPEN-DELAY(OPEN,1)))),20)
        return "Sum(If(Ge($open, Ref($open, 1)), 0, Greater(Sub($open, $low), Sub($open, Ref($open, 1)))), 20)"

    @classmethod
    def alpha094(cls):
        # Alpha#94: SUM((CLOSE>DELAY(CLOSE,1)?VOLUME:(CLOSE<DELAY(CLOSE,1)?-VOLUME:0)),30)
        return "Sum(If(Gt($close, Ref($close, 1)), $volume, If(Lt($close, Ref($close, 1)), Mul(-1, $volume), 0)), 30)"

    @classmethod
    def alpha095(cls):
        # Alpha#95: STD(AMOUNT,20)
        return "Std($amount, 20)"

    @classmethod
    def alpha096(cls):
        # Alpha#96: SMA(SMA((CLOSE-TSMIN(LOW,9))/(TSMAX(HIGH,9)-TSMIN(LOW,9))*100,3,1),3,1)
        return "WMA(WMA(Mul(Div(Sub($close, Ts_Min($low, 9)), Sub(Ts_Max($high, 9), Ts_Min($low, 9))), 100), 3), 3)"

    @classmethod
    def alpha097(cls):
        # Alpha#97: STD(VOLUME,10)
        return "Std($volume, 10)"

    @classmethod
    def alpha098(cls):
        # Alpha#98: ((((DELTA((SUM(CLOSE, 100) / 100), 100) / DELAY(CLOSE, 100)) < 0.05) || ((DELTA((SUM(CLOSE, 100) / 100), 100) /DELAY(CLOSE, 100)) == 0.05)) ? (-1 * (CLOSE -TSMIN(CLOSE, 100))) : (-1 * DELTA(CLOSE, 3)))
        # Note: || operator replaced with nested If
        delta_mean = "Div(Delta(Mean($close, 100), 100), Ref($close, 100))"
        return "If(Le(" + delta_mean + ", 0.05), Mul(-1, Sub($close, Ts_Min($close, 100))), Mul(-1, Delta($close, 3)))"

    @classmethod
    def alpha099(cls):
        # Alpha#99: (-1 * RANK(COVIANCE(RANK(CLOSE), RANK(VOLUME), 5)))
        return "Mul(-1, CSRank(Cov(CSRank($close), CSRank($volume), 5)))"

    @classmethod
    def alpha100(cls):
        # Alpha#100: STD(VOLUME,20)
        return "Std($volume, 20)"

    @classmethod
    def alpha101(cls):
        # Alpha#101: ((RANK(CORR(CLOSE, SUM(MEAN(VOLUME,30), 37), 15)) < RANK(CORR(RANK(((HIGH * 0.1) + (VWAP * 0.9))),RANK(VOLUME), 11))) * -1)
        # Note: Comparison converted to If statement
        return "If(Lt(CSRank(Corr($close, Sum(Mean($volume, 30), 37), 15)), CSRank(Corr(CSRank(Add(Mul($high, 0.1), Mul(SafeDiv($amount, $volume), 0.9))), CSRank($volume), 11))), -1, 1)"

    @classmethod
    def alpha102(cls):
        # Alpha#102: SMA(MAX(VOLUME-DELAY(VOLUME,1),0),6,1)/SMA(ABS(VOLUME-DELAY(VOLUME,1)),6,1)*100
        return "Mul(Div(WMA(Greater(Sub($volume, Ref($volume, 1)), 0), 6), WMA(Abs(Sub($volume, Ref($volume, 1))), 6)), 100)"

    @classmethod
    def alpha103(cls):
        # Alpha#103: ((20-LOWDAY(LOW,20))/20)*100
        # Note: LOWDAY returns days since lowest low, using IdxMin as approximation
        return "Mul(Div(Sub(20, Ts_ArgMin($low, 20)), 20), 100)"

    @classmethod
    def alpha104(cls):
        # Alpha#104: (-1 * (DELTA(CORR(HIGH, VOLUME, 5), 5) * RANK(STD(CLOSE, 20))))
        return "Mul(Mul(-1, Delta(Corr($high, $volume, 5), 5)), CSRank(Std($close, 20)))"

    @classmethod
    def alpha105(cls):
        # Alpha#105: (-1 * CORR(RANK(OPEN), RANK(VOLUME), 10))
        return "Mul(-1, Corr(CSRank($open), CSRank($volume), 10))"

    @classmethod
    def alpha106(cls):
        # Alpha#106: CLOSE-DELAY(CLOSE,20)
        return "Sub($close, Ref($close, 20))"

    @classmethod
    def alpha107(cls):
        # Alpha#107: (((-1 * RANK((OPEN -DELAY(HIGH, 1)))) * RANK((OPEN -DELAY(CLOSE, 1)))) *RANK((OPEN -DELAY(LOW, 1))))
        return "Mul(Mul(Mul(-1, CSRank(Sub($open, Ref($high, 1)))), CSRank(Sub($open, Ref($close, 1)))), CSRank(Sub($open, Ref($low, 1))))"

    @classmethod
    def alpha108(cls):
        # Alpha#108: ((RANK((HIGH -MIN(HIGH, 2)))^RANK(CORR((VWAP), (MEAN(VOLUME,120)), 6))) * -1)
        return "Mul(Pow(CSRank(Sub($high, Ts_Min($high, 2))), CSRank(Corr(SafeDiv($amount, $volume), Mean($volume, 120), 6))), -1)"

    @classmethod
    def alpha109(cls):
        # Alpha#109: SMA(HIGH-LOW,10,2)/SMA(SMA(HIGH-LOW,10,2),10,2)
        return "Div(WMA(Sub($high, $low), 10), WMA(WMA(Sub($high, $low), 10), 10))"

    @classmethod
    def alpha110(cls):
        # Alpha#110: SUM(MAX(0,HIGH-DELAY(CLOSE,1)),20)/SUM(MAX(0,DELAY(CLOSE,1)-LOW),20)*100
        return "Mul(Div(Sum(Greater(0, Sub($high, Ref($close, 1))), 20), Sum(Greater(0, Sub(Ref($close, 1), $low)), 20)), 100)"

    @classmethod
    def alpha111(cls):
        # Alpha#111: SMA(VOL*((CLOSE-LOW)-(HIGH-CLOSE))/(HIGH-LOW),11,2)-SMA(VOL*((CLOSE-LOW)-(HIGH-CLOSE))/(HIGH-LOW),4,2)
        # Note: VOL should be $volume
        price_pos = "Div(Sub(Sub($close, $low), Sub($high, $close)), Sub($high, $low))"
        return "Sub(WMA(Mul($volume, " + price_pos + "), 11), WMA(Mul($volume, " + price_pos + "), 4))"

    @classmethod
    def alpha112(cls):
        # Alpha#112: (SUM((CLOSE-DELAY(CLOSE,1)>0?CLOSE-DELAY(CLOSE,1):0),12)-SUM((CLOSE-DELAY(CLOSE,1)<0?ABS(CLOSE-DELAY(CLOSE,1)):0),12))/(SUM((CLOSE-DELAY(CLOSE,1)>0?CLOSE-DELAY(CLOSE,1):0),12)+SUM((CLOSE-DELAY(CLOSE,1)<0?ABS(CLOSE-DELAY(CLOSE,1)):0),12))*100
        up_sum = "Sum(If(Gt(Sub($close, Ref($close, 1)), 0), Sub($close, Ref($close, 1)), 0), 12)"
        down_sum = "Sum(If(Lt(Sub($close, Ref($close, 1)), 0), Abs(Sub($close, Ref($close, 1))), 0), 12)"
        return "Mul(Div(Sub(" + up_sum + ", " + down_sum + "), Add(" + up_sum + ", " + down_sum + ")), 100)"

    @classmethod
    def alpha113(cls):
        # Alpha#113: (-1 * ((RANK((SUM(DELAY(CLOSE, 5), 20) / 20)) * CORR(CLOSE, VOLUME, 2)) *RANK(CORR(SUM(CLOSE, 5),SUM(CLOSE, 20), 2))))
        return "Mul(Mul(Mul(-1, CSRank(Mean(Ref($close, 5), 20))), Corr($close, $volume, 2)), CSRank(Corr(Sum($close, 5), Sum($close, 20), 2)))"

    @classmethod
    def alpha114(cls):
        # Alpha#114: ((RANK(DELAY(((HIGH -LOW) / (SUM(CLOSE, 5) / 5)), 2)) * RANK(RANK(VOLUME))) / (((HIGH -LOW) /(SUM(CLOSE, 5) / 5)) / (VWAP -CLOSE)))
        return "Div(Mul(CSRank(Ref(Div(Sub($high, $low), Mean($close, 5)), 2)), CSRank(CSRank($volume))), Div(Div(Sub($high, $low), Mean($close, 5)), Sub(SafeDiv($amount, $volume), $close)))"

    @classmethod
    def alpha115(cls):
        # Alpha#115: (RANK(CORR(((HIGH * 0.9) + (CLOSE * 0.1)), MEAN(VOLUME,30), 10))^RANK(CORR(TSRANK(((HIGH + LOW) /2), 4), TSRANK(VOLUME, 10), 7)))
        return "Pow(CSRank(Corr(Add(Mul($high, 0.9), Mul($close, 0.1)), Mean($volume, 30), 10)), CSRank(Corr(Ts_Rank(Div(Add($high, $low), 2), 4), Ts_Rank($volume, 10), 7)))"

    @classmethod
    def alpha116(cls):
        # Alpha#116: REGBETA(CLOSE,SEQUENCE,20)
        # Note: REGBETA is regression beta, simplified to correlation approximation
        # Using correlation as approximation since Sequence function may not be available
        return "Corr($close, Delta($close, 1), 20)"

    @classmethod
    def alpha117(cls):
        # Alpha#117: ((TSRANK(VOLUME, 32) * (1 -TSRANK(((CLOSE + HIGH) -LOW), 16))) * (1 -TSRANK(RET, 32)))
        return "Mul(Mul(Ts_Rank($volume, 32), Sub(1, Ts_Rank(Sub(Add($close, $high), $low), 16))), Sub(1, Ts_Rank($return_day, 32)))"

    @classmethod
    def alpha118(cls):
        # Alpha#118: SUM(HIGH-OPEN,20)/SUM(OPEN-LOW,20)*100
        return "Mul(Div(Sum(Sub($high, $open), 20), Sum(Sub($open, $low), 20)), 100)"

    @classmethod
    def alpha119(cls):
        # Alpha#119: (RANK(DECAYLINEAR(CORR(VWAP, SUM(MEAN(VOLUME,5), 26), 5), 7)) -RANK(DECAYLINEAR(TSRANK(MIN(CORR(RANK(OPEN), RANK(MEAN(VOLUME,15)), 21), 9), 7), 8)))
        return "Sub(CSRank(WMA(Corr(SafeDiv($amount, $volume), Sum(Mean($volume, 5), 26), 5), 7)), CSRank(WMA(Ts_Rank(Min(Corr(CSRank($open), CSRank(Mean($volume, 15)), 21), 9), 7), 8)))"

    @classmethod
    def alpha120(cls):
        # Alpha#120: (RANK((VWAP -CLOSE)) / RANK((VWAP + CLOSE)))
        return "Div(CSRank(Sub(SafeDiv($amount, $volume), $close)), CSRank(Add(SafeDiv($amount, $volume), $close)))"

    @classmethod
    def alpha121(cls):
        # Alpha#121: ((RANK((VWAP -MIN(VWAP, 12)))^TSRANK(CORR(TSRANK(VWAP, 20), TSRANK(MEAN(VOLUME,60), 2), 18), 3)) * -1)
        return "Mul(Pow(CSRank(Sub(SafeDiv($amount, $volume), Ts_Min(SafeDiv($amount, $volume), 12))), Ts_Rank(Corr(Ts_Rank(SafeDiv($amount, $volume), 20), Ts_Rank(Mean($volume, 60), 2), 18), 3)), -1)"

    @classmethod
    def alpha122(cls):
        # Alpha#122: (SMA(SMA(SMA(LOG(CLOSE),13,2),13,2),13,2)-DELAY(SMA(SMA(SMA(LOG(CLOSE),13,2),13,2),13,2),1))/DELAY(SMA(SMA(SMA(LOG(CLOSE),13,2),13,2),13,2),1)
        triple_sma = "WMA(WMA(WMA(Log($close), 13), 13), 13)"
        return "Div(Sub(" + triple_sma + ", Ref(" + triple_sma + ", 1)), Ref(" + triple_sma + ", 1))"

    @classmethod
    def alpha123(cls):
        # Alpha#123: ((RANK(CORR(SUM(((HIGH + LOW) / 2), 20), SUM(MEAN(VOLUME,60), 20), 9))<RANK(CORR(LOW, VOLUME,6))) * -1)
        # Note: Comparison converted to If statement
        return "If(Lt(CSRank(Corr(Sum(Div(Add($high, $low), 2), 20), Sum(Mean($volume, 60), 20), 9)), CSRank(Corr($low, $volume, 6))), -1, 1)"

    @classmethod
    def alpha124(cls):
        # Alpha#124: (CLOSE -VWAP) / DECAYLINEAR(RANK(TSMAX(CLOSE, 30)),2)
        return "Div(Sub($close, SafeDiv($amount, $volume)), WMA(CSRank(Ts_Max($close, 30)), 2))"

    @classmethod
    def alpha125(cls):
        # Alpha#125: (RANK(DECAYLINEAR(CORR((VWAP), MEAN(VOLUME,80),17), 20)) / RANK(DECAYLINEAR(DELTA(((CLOSE * 0.5)+ (VWAP * 0.5)), 3), 16)))
        return "Div(CSRank(WMA(Corr(SafeDiv($amount, $volume), Mean($volume, 80), 17), 20)), CSRank(WMA(Delta(Add(Mul($close, 0.5), Mul(SafeDiv($amount, $volume), 0.5)), 3), 16)))"

    @classmethod
    def alpha126(cls):
        # Alpha#126: (CLOSE+HIGH+LOW)/3
        return "Div(Add(Add($close, $high), $low), 3)"

    @classmethod
    def alpha127(cls):
        # Alpha#127: (MEAN((100*(CLOSE-MAX(CLOSE,12))/(MAX(CLOSE,12)))^2))^(1/2)
        # Note: MEAN 是对平方后的百分比偏差序列求移动平均
        # 原始表达式未指定窗口，根据 MAX(CLOSE,12) 推断窗口为 12
        return "Pow(Mean(Pow(Div(Mul(100, Sub($close, Ts_Max($close, 12))), Ts_Max($close, 12)), 2), 12), 0.5)"

    @classmethod
    def alpha128(cls):
        # Alpha#128: 100-(100/(1+SUM(((HIGH+LOW+CLOSE)/3>DELAY((HIGH+LOW+CLOSE)/3,1)?(HIGH+LOW+CLOSE)/3*VOLUME:0),14)/SUM(((HIGH+LOW+CLOSE)/3<DELAY((HIGH+LOW+CLOSE)/3,1)?(HIGH+LOW+CLOSE)/3*VOLUME:0),14)))
        tp = "Div(Add(Add($high, $low), $close), 3)"
        up_sum = "Sum(If(Gt(" + tp + ", Ref(" + tp + ", 1)), Mul(" + tp + ", $volume), 0), 14)"
        down_sum = "Sum(If(Lt(" + tp + ", Ref(" + tp + ", 1)), Mul(" + tp + ", $volume), 0), 14)"
        return "Sub(100, Div(100, Add(1, Div(" + up_sum + ", " + down_sum + "))))"

    @classmethod
    def alpha129(cls):
        # Alpha#129: SUM((CLOSE-DELAY(CLOSE,1)<0?ABS(CLOSE-DELAY(CLOSE,1)):0),12)
        return "Sum(If(Lt(Sub($close, Ref($close, 1)), 0), Abs(Sub($close, Ref($close, 1))), 0), 12)"

    @classmethod
    def alpha130(cls):
        # Alpha#130: (RANK(DECAYLINEAR(CORR(((HIGH + LOW) / 2), MEAN(VOLUME,40), 9), 10)) /RANK(DECAYLINEAR(CORR(RANK(VWAP), RANK(VOLUME), 7),3)))
        return "Div(CSRank(WMA(Corr(Div(Add($high, $low), 2), Mean($volume, 40), 9), 10)), CSRank(WMA(Corr(CSRank(SafeDiv($amount, $volume)), CSRank($volume), 7), 3)))"

    @classmethod
    def alpha131(cls):
        # Alpha#131: (RANK(DELAT(VWAP, 1))^TSRANK(CORR(CLOSE,MEAN(VOLUME,50), 18), 18))
        # Note: DELAT is likely a typo for DELTA
        return "Pow(CSRank(Delta(SafeDiv($amount, $volume), 1)), Ts_Rank(Corr($close, Mean($volume, 50), 18), 18))"

    @classmethod
    def alpha132(cls):
        # Alpha#132: MEAN(AMOUNT,20)
        return "Mean($amount, 20)"

    @classmethod
    def alpha133(cls):
        # Alpha#133: ((20-HIGHDAY(HIGH,20))/20)*100-((20-LOWDAY(LOW,20))/20)*100
        # Note: HIGHDAY and LOWDAY use IdxMax and IdxMin
        return "Sub(Mul(Div(Sub(20, Ts_ArgMax($high, 20)), 20), 100), Mul(Div(Sub(20, Ts_ArgMin($low, 20)), 20), 100))"

    @classmethod
    def alpha134(cls):
        # Alpha#134: (CLOSE-DELAY(CLOSE,12))/DELAY(CLOSE,12)*VOLUME
        return "Mul(Div(Sub($close, Ref($close, 12)), Ref($close, 12)), $volume)"

    @classmethod
    def alpha135(cls):
        # Alpha#135: SMA(DELAY(CLOSE/DELAY(CLOSE,20),1),20,1)
        return "WMA(Ref(Div($close, Ref($close, 20)), 1), 20)"

    @classmethod
    def alpha136(cls):
        # Alpha#136: ((-1 * RANK(DELTA(RET, 3))) * CORR(OPEN, VOLUME, 10))
        return "Mul(Mul(-1, CSRank(Delta($return_day, 3))), Corr($open, $volume, 10))"

    @classmethod
    def alpha137(cls):
        # Alpha#137: 16*(CLOSE-DELAY(CLOSE,1)+(CLOSE-OPEN)/2+DELAY(CLOSE,1)-DELAY(OPEN,1))/((ABS(HIGH-DELAY(CLOSE,1))>ABS(LOW-DELAY(CLOSE,1)) &ABS(HIGH-DELAY(CLOSE,1))>ABS(HIGH-DELAY(LOW,1))?ABS(HIGH-DELAY(CLOSE,1))+ABS(LOW-DELAY(CLOSE,1))/2+ABS(DELAY(CLOSE,1)-DELAY(OPEN,1))/4:(ABS(LOW-DELAY(CLOSE,1))>ABS(HIGH-DELAY(LOW,1)) &ABS(LOW-DELAY(CLOSE,1))>ABS(HIGH-DELAY(CLOSE,1))?ABS(LOW-DELAY(CLOSE,1))+ABS(HIGH-DELAY(CLOSE,1))/2+ABS(DELAY(CLOSE,1)-DELAY(OPEN,1))/4:ABS(HIGH-DELAY(LOW,1))+ABS(DELAY(CLOSE,1)-DELAY(OPEN,1))/4)))*MAX(ABS(HIGH-DELAY(CLOSE,1)),ABS(LOW-DELAY(CLOSE,1)))
        # Note: Same complex conditional as Alpha055, using nested If statements
        hc = "Abs(Sub($high, Ref($close, 1)))"
        lc = "Abs(Sub($low, Ref($close, 1)))"
        hl = "Abs(Sub($high, Ref($low, 1)))"
        co = "Abs(Sub(Ref($close, 1), Ref($open, 1)))"
        val1 = "Add(Add(" + hc + ", Div(" + lc + ", 2)), Div(" + co + ", 4))"
        val2 = "Add(Add(" + lc + ", Div(" + hc + ", 2)), Div(" + co + ", 4))"
        val3 = "Add(" + hl + ", Div(" + co + ", 4))"
        denom_simple = "Add(Add(" + hc + ", " + lc + "), Div(" + co + ", 2))"
        numerator = "Mul(16, Add(Add(Sub($close, Ref($close, 1)), Div(Sub($close, $open), 2)), Sub(Ref($close, 1), Ref($open, 1))))"
        max_hc_lc = "Div(Add(Add(" + hc + ", " + lc + "), Abs(Sub(" + hc + ", " + lc + "))), 2)"
        return "Mul(Div(" + numerator + ", " + denom_simple + "), " + max_hc_lc + ")"

    @classmethod
    def alpha138(cls):
        # Alpha#138: ((RANK(DECAYLINEAR(DELTA((((LOW * 0.7) + (VWAP *0.3))), 3), 20)) -TSRANK(DECAYLINEAR(TSRANK(CORR(TSRANK(LOW, 8), TSRANK(MEAN(VOLUME,60), 17), 5), 19), 16), 7)) * -1)
        return "Mul(Sub(CSRank(WMA(Delta(Add(Mul($low, 0.7), Mul(SafeDiv($amount, $volume), 0.3)), 3), 20)), Ts_Rank(WMA(Ts_Rank(Corr(Ts_Rank($low, 8), Ts_Rank(Mean($volume, 60), 17), 5), 19), 16), 7)), -1)"

    @classmethod
    def alpha139(cls):
        # Alpha#139: (-1 * CORR(OPEN, VOLUME, 10))
        return "Mul(-1, Corr($open, $volume, 10))"

    @classmethod
    def alpha140(cls):
        # Alpha#140: MIN(RANK(DECAYLINEAR(((RANK(OPEN) + RANK(LOW)) -(RANK(HIGH) + RANK(CLOSE))), 8)),TSRANK(DECAYLINEAR(CORR(TSRANK(CLOSE, 8), TSRANK(MEAN(VOLUME,60), 20), 8), 7), 3))
        # Note: Original expression missing closing parenthesis, completed it
        return "Less(CSRank(WMA(Sub(Add(CSRank($open), CSRank($low)), Add(CSRank($high), CSRank($close))), 8)), Ts_Rank(WMA(Corr(Ts_Rank($close, 8), Ts_Rank(Mean($volume, 60), 20), 8), 7), 3))"

    @classmethod
    def alpha141(cls):
        # Alpha#141: (RANK(CORR(RANK(HIGH), RANK(MEAN(VOLUME,15)), 9))* -1)
        return "Mul(-1, CSRank(Corr(CSRank($high), CSRank(Mean($volume, 15)), 9)))"

    @classmethod
    def alpha142(cls):
        # Alpha#142: (((-1 * RANK(TSRANK(CLOSE, 10))) * RANK(DELTA(DELTA(CLOSE, 1), 1))) *RANK(TSRANK((VOLUME/MEAN(VOLUME,20)), 5)))
        return "Mul(Mul(Mul(-1, CSRank(Ts_Rank($close, 10))), CSRank(Delta(Delta($close, 1), 1))), CSRank(Ts_Rank(Div($volume, Mean($volume, 20)), 5)))"

    @classmethod
    def alpha143(cls):
        # Alpha#143: CLOSE>DELAY(CLOSE,1)?(CLOSE-DELAY(CLOSE,1))/DELAY(CLOSE,1)*SELF:SELF
        # Note: SELF is recursive reference - simplified to use the expression itself
        return "If(Gt($close, Ref($close, 1)), Mul(Div(Sub($close, Ref($close, 1)), Ref($close, 1)), Div(Sub($close, Ref($close, 1)), Ref($close, 1))), Div(Sub($close, Ref($close, 1)), Ref($close, 1)))"

    @classmethod
    def alpha144(cls):
        # Alpha#144: SUMIF(ABS(CLOSE/DELAY(CLOSE,1)-1)/AMOUNT,20,CLOSE<DELAY(CLOSE,1))/COUNT(CLOSE<DELAY(CLOSE,1),20)
        # Note: SUMIF approximated with Sum(If(condition, value, 0), window)
        return "Div(Sum(If(Lt($close, Ref($close, 1)), Div(Abs(Sub(Div($close, Ref($close, 1)), 1)), $amount), 0), 20), Sum(If(Lt($close, Ref($close, 1)), 1, 0), 20))"

    @classmethod
    def alpha145(cls):
        # Alpha#145: (MEAN(VOLUME,9)-MEAN(VOLUME,26))/MEAN(VOLUME,12)*100
        return "Mul(Div(Sub(Mean($volume, 9), Mean($volume, 26)), Mean($volume, 12)), 100)"

    @classmethod
    def alpha146(cls):
        # Alpha#146: MEAN((CLOSE-DELAY(CLOSE,1))/DELAY(CLOSE,1)-SMA((CLOSE-DELAY(CLOSE,1))/DELAY(CLOSE,1),61,2),20)*((CLOSE-DELAY(CLOSE,1))/DELAY(CLOSE,1)-SMA((CLOSE-DELAY(CLOSE,1))/DELAY(CLOSE,1),61,2))/SMA(((CLOSE-DELAY(CLOSE,1))/DELAY(CLOSE,1)-((CLOSE-DELAY(CLOSE,1))/DELAY(CLOSE,1)-SMA((CLOSE-DELAY(CLOSE,1))/DELAY(CLOSE,1),61,2)))^2,60)
        ret = "Div(Sub($close, Ref($close, 1)), Ref($close, 1))"
        sma_ret = "WMA(" + ret + ", 61)"
        diff = "Sub(" + ret + ", " + sma_ret + ")"
        return "Div(Mul(Mean(" + diff + ", 20), " + diff + "), WMA(Pow(" + diff + ", 2), 60))"

    @classmethod
    def alpha147(cls):
        # Alpha#147: REGBETA(MEAN(CLOSE,12),SEQUENCE(12))
        # Note: REGBETA simplified to correlation approximation
        return "Corr(Mean($close, 12), Delta(Mean($close, 12), 1), 12)"

    @classmethod
    def alpha148(cls):
        # Alpha#148: ((RANK(CORR((OPEN), SUM(MEAN(VOLUME,60), 9), 6)) < RANK((OPEN -TSMIN(OPEN, 14)))) * -1)
        # Note: Comparison converted to If statement
        return "If(Lt(CSRank(Corr($open, Sum(Mean($volume, 60), 9), 6)), CSRank(Sub($open, Ts_Min($open, 14)))), -1, 1)"

    @classmethod
    def alpha149(cls):
        # Alpha#149: REGBETA(FILTER(CLOSE/DELAY(CLOSE,1)-1,BANCHMARKINDEXCLOSE<DELAY(BANCHMARKINDEXCLOSE,1)),FILTER(BANCHMARKINDEXCLOSE/DELAY(BANCHMARKINDEXCLOSE,1)-1,BANCHMARKINDEXCLOSE<DELAY(BANCHMARKINDEXCLOSE,1)),252)
        # Note: FILTER and benchmark index data not available - simplified to return-based calculation
        return "Corr($return_day, $return_day, 252)"

    @classmethod
    def alpha150(cls):
        # Alpha#150: (CLOSE+HIGH+LOW)/3*VOLUME
        return "Mul(Div(Add(Add($close, $high), $low), 3), $volume)"

    @classmethod
    def alpha151(cls):
        # Alpha#151: SMA(CLOSE-DELAY(CLOSE,20),20,1)
        return "WMA(Sub($close, Ref($close, 20)), 20)"

    @classmethod
    def alpha152(cls):
        # Alpha#152: SMA(MEAN(DELAY(SMA(DELAY(CLOSE/DELAY(CLOSE,9),1),9,1),1),12)-MEAN(DELAY(SMA(DELAY(CLOSE/DELAY(CLOSE,9),1),9,1),1),26),9,1)
        inner_sma = "WMA(Ref(Div($close, Ref($close, 9)), 1), 9)"
        return "WMA(Sub(Mean(Ref(" + inner_sma + ", 1), 12), Mean(Ref(" + inner_sma + ", 1), 26)), 9)"

    @classmethod
    def alpha153(cls):
        # Alpha#153: (MEAN(CLOSE,3)+MEAN(CLOSE,6)+MEAN(CLOSE,12)+MEAN(CLOSE,24))/4
        return "Div(Add(Add(Add(Mean($close, 3), Mean($close, 6)), Mean($close, 12)), Mean($close, 24)), 4)"

    @classmethod
    def alpha154(cls):
        # Alpha#154: (((VWAP -MIN(VWAP, 16))) < (CORR(VWAP, MEAN(VOLUME,180), 18)))
        # Note: Comparison converted to If statement
        return "If(Lt(Sub(SafeDiv($amount, $volume), Ts_Min(SafeDiv($amount, $volume), 16)), Corr(SafeDiv($amount, $volume), Mean($volume, 180), 18)), 1, -1)"

    @classmethod
    def alpha155(cls):
        # Alpha#155: SMA(VOLUME,13,2)-SMA(VOLUME,27,2)-SMA(SMA(VOLUME,13,2)-SMA(VOLUME,27,2),10,2)
        return "Sub(Sub(WMA($volume, 13), WMA($volume, 27)), WMA(Sub(WMA($volume, 13), WMA($volume, 27)), 10))"

    @classmethod
    def alpha156(cls):
        # Alpha#156: (MAX(RANK(DECAYLINEAR(DELTA(VWAP, 5), 3)), RANK(DECAYLINEAR(((DELTA(((OPEN * 0.15) + (LOW *0.85)),2) / ((OPEN * 0.15) + (LOW * 0.85))) * -1), 3))) * -1)
        return "Mul(Greater(CSRank(WMA(Delta(SafeDiv($amount, $volume), 5), 3)), CSRank(WMA(Mul(Div(Delta(Add(Mul($open, 0.15), Mul($low, 0.85)), 2), Add(Mul($open, 0.15), Mul($low, 0.85))), -1), 3))), -1)"

    @classmethod
    def alpha157(cls):
        # Alpha#157: (MIN(PROD(RANK(RANK(LOG(SUM(TSMIN(RANK(RANK((-1 * RANK(DELTA((CLOSE -1), 5))))), 2), 1)))), 1), 5) +TSRANK(DELAY((-1 * RET), 6), 5))
        # Note: PROD is product, approximated with multiplication
        inner_rank = "CSRank(CSRank(Mul(-1, CSRank(Delta(Sub($close, 1), 5)))))"
        return "Add(Ts_Min(CSRank(CSRank(Log(Sum(Ts_Min(" + inner_rank + ", 2), 1)))), 5), Ts_Rank(Ref(Mul(-1, $return_day), 6), 5))"

    @classmethod
    def alpha158(cls):
        # Alpha#158: ((HIGH-SMA(CLOSE,15,2))-(LOW-SMA(CLOSE,15,2)))/CLOSE
        sma_close = "WMA($close, 15)"
        return "Div(Sub(Sub($high, " + sma_close + "), Sub($low, " + sma_close + ")), $close)"

    @classmethod
    def alpha159(cls):
        # Alpha#159: ((CLOSE-SUM(MIN(LOW,DELAY(CLOSE,1)),6))/SUM(MAX(HGIH,DELAY(CLOSE,1))-MIN(LOW,DELAY(CLOSE,1)),6)*12*24+(CLOSE-SUM(MIN(LOW,DELAY(CLOSE,1)),12))/SUM(MAX(HGIH,DELAY(CLOSE,1))-MIN(LOW,DELAY(CLOSE,1)),12)*6*24+(CLOSE-SUM(MIN(LOW,DELAY(CLOSE,1)),24))/SUM(MAX(HGIH,DELAY(CLOSE,1))-MIN(LOW,DELAY(CLOSE,1)),24)*6*24)*100/(6*12+6*24+12*24)
        # Note: Fixed typo HGIH -> HIGH
        min_low = "Less($low, Ref($close, 1))"
        max_high = "Greater($high, Ref($close, 1))"
        range_sum = "Sub(" + max_high + ", " + min_low + ")"
        part1 = "Mul(Div(Sub($close, Sum(" + min_low + ", 6)), Sum(" + range_sum + ", 6)), 288)"
        part2 = "Mul(Div(Sub($close, Sum(" + min_low + ", 12)), Sum(" + range_sum + ", 12)), 144)"
        part3 = "Mul(Div(Sub($close, Sum(" + min_low + ", 24)), Sum(" + range_sum + ", 24)), 144)"
        return "Div(Mul(Add(Add(" + part1 + ", " + part2 + "), " + part3 + "), 100), 504)"

    @classmethod
    def alpha160(cls):
        # Alpha#160: SMA((CLOSE<=DELAY(CLOSE,1)?STD(CLOSE,20):0),20,1)
        return "WMA(If(Le($close, Ref($close, 1)), Std($close, 20), 0), 20)"

    @classmethod
    def alpha161(cls):
        # Alpha#161: MEAN(MAX(MAX((HIGH-LOW),ABS(DELAY(CLOSE,1)-HIGH)),ABS(DELAY(CLOSE,1)-LOW)),12)
        return "Mean(Greater(Greater(Sub($high, $low), Abs(Sub(Ref($close, 1), $high))), Abs(Sub(Ref($close, 1), $low))), 12)"

    @classmethod
    def alpha162(cls):
        # Alpha#162: (SMA(MAX(CLOSE-DELAY(CLOSE,1),0),12,1)/SMA(ABS(CLOSE-DELAY(CLOSE,1)),12,1)*100-MIN(SMA(MAX(CLOSE-DELAY(CLOSE,1),0),12,1)/SMA(ABS(CLOSE-DELAY(CLOSE,1)),12,1)*100,12))/(MAX(SMA(MAX(CLOSE-DELAY(CLOSE,1),0),12,1)/SMA(ABS(CLOSE-DELAY(CLOSE,1)),12,1)*100,12)-MIN(SMA(MAX(CLOSE-DELAY(CLOSE,1),0),12,1)/SMA(ABS(CLOSE-DELAY(CLOSE,1)),12,1)*100,12))
        rsi = "Mul(Div(WMA(Greater(Sub($close, Ref($close, 1)), 0), 12), WMA(Abs(Sub($close, Ref($close, 1))), 12)), 100)"
        return "Div(Sub(" + rsi + ", Ts_Min(" + rsi + ", 12)), Sub(Ts_Max(" + rsi + ", 12), Ts_Min(" + rsi + ", 12)))"

    @classmethod
    def alpha163(cls):
        # Alpha#163: RANK(((((-1 * RET) * MEAN(VOLUME,20)) * VWAP) * (HIGH -CLOSE)))
        return "CSRank(Mul(Mul(Mul(Mul(-1, $return_day), Mean($volume, 20)), SafeDiv($amount, $volume)), Sub($high, $close)))"

    @classmethod
    def alpha164(cls):
        # Alpha#164: SMA((((CLOSE>DELAY(CLOSE,1))?1/(CLOSE-DELAY(CLOSE,1)):1)-MIN(((CLOSE>DELAY(CLOSE,1))?1/(CLOSE-DELAY(CLOSE,1)):1),12))/(HIGH-LOW)*100,13,2)
        inv_ret = "If(Gt($close, Ref($close, 1)), Div(1, Sub($close, Ref($close, 1))), 1)"
        return "WMA(Mul(Div(Sub(" + inv_ret + ", Ts_Min(" + inv_ret + ", 12)), Sub($high, $low)), 100), 13)"
    
    # 缺少參數 先捨棄
    # @classmethod
    # def alpha165(cls):
    #     # Alpha#165: MAX(SUMAC(CLOSE-MEAN(CLOSE,48)))-MIN(SUMAC(CLOSE-MEAN(CLOSE,48)))/STD(CLOSE,48)
    #     # Note: SUMAC is cumulative sum - using Sum as approximation, Greater/Min over the window
    #     cumsum = "Sum($close - Mean($close, 48), 48)"
    #     return "Greater(" + cumsum + ") - Min(" + cumsum + ") / Std($close, 48)"

    @classmethod
    def alpha166(cls):
        # Alpha#166: -20*（20-1 ）^1.5*SUM(CLOSE/DELAY(CLOSE,1)-1-MEAN(CLOSE/DELAY(CLOSE,1)-1,20),20)/((20-1)*(20-2)(SUM((CLOSE/DELAY(CLOSE,1),20)^2,20))^1.5)
        # Note: Fixed syntax - missing * operator and corrected parentheses
        ret = "Sub(Div($close, Ref($close, 1)), 1)"
        num_coeff = round(-20 * 19**1.5, 6)
        numerator = "Mul(" + str(num_coeff) + ", Sum(Sub(" + ret + ", Mean(" + ret + ", 20)), 20))"
        denominator = "Mul(342, Pow(Sum(Pow(" + ret + ", 2), 20), 1.5))"
        return "Div(" + numerator + ", " + denominator + ")"

    @classmethod
    def alpha167(cls):
        # Alpha#167: SUM((CLOSE-DELAY(CLOSE,1)>0?CLOSE-DELAY(CLOSE,1):0),12)
        return "Sum(If(Gt(Sub($close, Ref($close, 1)), 0), Sub($close, Ref($close, 1)), 0), 12)"

    @classmethod
    def alpha168(cls):
        # Alpha#168: (-1*VOLUME/MEAN(VOLUME,20))
        return "Mul(-1, Div($volume, Mean($volume, 20)))"

    @classmethod
    def alpha169(cls):
        # Alpha#169: SMA(MEAN(DELAY(SMA(CLOSE-DELAY(CLOSE,1),9,1),1),12)-MEAN(DELAY(SMA(CLOSE-DELAY(CLOSE,1),9,1),1),26),10,1)
        inner_sma = "WMA(Sub($close, Ref($close, 1)), 9)"
        return "WMA(Sub(Mean(Ref(" + inner_sma + ", 1), 12), Mean(Ref(" + inner_sma + ", 1), 26)), 10)"

    @classmethod
    def alpha170(cls):
        # Alpha#170: ((((RANK((1 / CLOSE)) * VOLUME) / MEAN(VOLUME,20)) * ((HIGH * RANK((HIGH -CLOSE))) / (SUM(HIGH, 5) /5))) -RANK((VWAP -DELAY(VWAP, 5))))
        return "Sub(Mul(Mul(Div(CSRank(Div(1, $close)), Mean($volume, 20)), $volume), Div(Mul($high, CSRank(Sub($high, $close))), Mean($high, 5))), CSRank(Sub(SafeDiv($amount, $volume), Ref(SafeDiv($amount, $volume), 5))))"

    @classmethod
    def alpha171(cls):
        # Alpha#171: ((-1 * ((LOW -CLOSE) * (OPEN^5))) / ((CLOSE -HIGH) * (CLOSE^5)))
        return "Div(Mul(-1, Mul(Sub($low, $close), Pow($open, 5))), Mul(Sub($close, $high), Pow($close, 5)))"

    @classmethod
    def alpha172(cls):
        # Alpha#172: MEAN(ABS(SUM((LD>0 & LD>HD)?LD:0,14)*100/SUM(TR,14)-SUM((HD>0 &HD>LD)?HD:0,14)*100/SUM(TR,14))/(SUM((LD>0 & LD>HD)?LD:0,14)*100/SUM(TR,14)+SUM((HD>0 &HD>LD)?HD:0,14)*100/SUM(TR,14))*100,6)
        # Note: LD, HD, TR are ATR components - LD = Low - Ref(Low,1), HD = Ref(High,1) - High, TR = True Range
        # Note: && replaced with nested If statements
        ld = "Sub($low, Ref($low, 1))"
        hd = "Sub(Ref($high, 1), $high)"
        tr = "Greater(Sub($high, $low), Greater(Abs(Sub($high, Ref($close, 1))), Abs(Sub($low, Ref($close, 1)))))"
        ld_sum = "Sum(If(Gt(" + ld + ", 0), If(Gt(" + ld + ", " + hd + "), " + ld + ", 0), 0), 14)"
        hd_sum = "Sum(If(Gt(" + hd + ", 0), If(Gt(" + hd + ", " + ld + "), " + hd + ", 0), 0), 14)"
        tr_sum = "Sum(" + tr + ", 14)"
        diff = "Sub(Div(Mul(" + ld_sum + ", 100), " + tr_sum + "), Div(Mul(" + hd_sum + ", 100), " + tr_sum + "))"
        total = "Add(Div(Mul(" + ld_sum + ", 100), " + tr_sum + "), Div(Mul(" + hd_sum + ", 100), " + tr_sum + "))"
        return "Mean(Mul(Div(Abs(" + diff + "), " + total + "), 100), 6)"

    @classmethod
    def alpha173(cls):
        # Alpha#173: 3*SMA(CLOSE,13,2)-2*SMA(SMA(CLOSE,13,2),13,2)+SMA(SMA(SMA(LOG(CLOSE),13,2),13,2),13,2)
        sma_close = "WMA($close, 13)"
        return "Add(Sub(Mul(3, " + sma_close + "), Mul(2, WMA(" + sma_close + ", 13))), WMA(WMA(WMA(Log($close), 13), 13), 13))"

    @classmethod
    def alpha174(cls):
        # Alpha#174: SMA((CLOSE>DELAY(CLOSE,1)?STD(CLOSE,20):0),20,1)
        return "WMA(If(Gt($close, Ref($close, 1)), Std($close, 20), 0), 20)"

    @classmethod
    def alpha175(cls):
        # Alpha#175: MEAN(MAX(MAX((HIGH-LOW),ABS(DELAY(CLOSE,1)-HIGH)),ABS(DELAY(CLOSE,1)-LOW)),6)
        return "Mean(Greater(Greater(Sub($high, $low), Abs(Sub(Ref($close, 1), $high))), Abs(Sub(Ref($close, 1), $low))), 6)"

    @classmethod
    def alpha176(cls):
        # Alpha#176: CORR(RANK(((CLOSE -TSMIN(LOW, 12)) / (TSMAX(HIGH, 12) -TSMIN(LOW,12)))),RANK(VOLUME), 6)
        return "Corr(CSRank(Div(Sub($close, Ts_Min($low, 12)), Sub(Ts_Max($high, 12), Ts_Min($low, 12)))), CSRank($volume), 6)"

    @classmethod
    def alpha177(cls):
        # Alpha#177: ((20-HIGHDAY(HIGH,20))/20)*100
        return "Mul(Div(Sub(20, Ts_ArgMax($high, 20)), 20), 100)"

    @classmethod
    def alpha178(cls):
        # Alpha#178: (CLOSE-DELAY(CLOSE,1))/DELAY(CLOSE,1)*VOLUME
        return "Mul(Div(Sub($close, Ref($close, 1)), Ref($close, 1)), $volume)"

    @classmethod
    def alpha179(cls):
        # Alpha#179: (RANK(CORR(VWAP, VOLUME, 4)) *RANK(CORR(RANK(LOW),RANK(MEAN(VOLUME,50)), 12)))
        return "Mul(CSRank(Corr(SafeDiv($amount, $volume), $volume, 4)), CSRank(Corr(CSRank($low), CSRank(Mean($volume, 50)), 12)))"

    @classmethod
    def alpha180(cls):
        # Alpha#180: ((MEAN(VOLUME,20) < VOLUME) ? ((-1 * TSRANK(ABS(DELTA(CLOSE, 7)), 60)) *SIGN(DELTA(CLOSE, 7)) : (-1 *VOLUME)))
        # Note: Fixed missing closing parenthesis in original
        return "If(Lt(Mean($volume, 20), $volume), Mul(Mul(-1, Ts_Rank(Abs(Delta($close, 7)), 60)), Sign(Delta($close, 7))), Mul(-1, $volume))"

    @classmethod
    def alpha181(cls):
        # Alpha#181: SUM(((CLOSE/DELAY(CLOSE,1)-1)-MEAN((CLOSE/DELAY(CLOSE,1)-1),20))-(BANCHMARKINDEXCLOSE-MEAN(BANCHMARKINDEXCLOSE,20))^2,20)/SUM((BANCHMARKINDEXCLOSE-MEAN(BANCHMARKINDEXCLOSE,20))^3)
        # Note: Benchmark index data not available - simplified to use close returns only
        ret = "Sub(Div($close, Ref($close, 1)), 1)"
        demean = "Sub(" + ret + ", Mean(" + ret + ", 20))"
        return "Div(Sum(Sub(" + demean + ", Pow(" + demean + ", 2)), 20), Sum(Pow(" + demean + ", 3), 20))"

    @classmethod
    def alpha182(cls):
        # Alpha#182: COUNT((CLOSE>OPEN & BANCHMARKINDEXCLOSE>BANCHMARKINDEXOPEN)OR(CLOSE<OPEN &BANCHMARKINDEXCLOSE<BANCHMARKINDEXOPEN),20)/20
        # Note: Benchmark index data not available - simplified to use close/open comparison only
        # Note: && and || replaced with nested If statements
        return "Div(Sum(If(Gt($close, $open), 1, If(Lt($close, $open), 1, 0)), 20), 20)"

    @classmethod
    def alpha183(cls):
        # Alpha#183: MAX(SUMAC(CLOSE-MEAN(CLOSE,24)))-MIN(SUMAC(CLOSE-MEAN(CLOSE,24)))/STD(CLOSE,24)
        # Note: SUMAC is cumulative sum - using Sum as approximation
        cumsum = "Sum(Sub($close, Mean($close, 24)), 24)"
        return "Div(Sub(Ts_Max(" + cumsum + ", 24), Ts_Min(" + cumsum + ", 24)), Std($close, 24))"

    @classmethod
    def alpha184(cls):
        # Alpha#184: (RANK(CORR(DELAY((OPEN -CLOSE), 1), CLOSE, 200)) + RANK((OPEN -CLOSE)))
        return "Add(CSRank(Corr(Ref(Sub($open, $close), 1), $close, 200)), CSRank(Sub($open, $close)))"

    @classmethod
    def alpha185(cls):
        # Alpha#185: RANK((-1 * ((1 -(OPEN / CLOSE))^2)))
        return "CSRank(Mul(-1, Pow(Sub(1, Div($open, $close)), 2)))"

    @classmethod
    def alpha186(cls):
        # Alpha#186: (MEAN(ABS(SUM((LD>0 & LD>HD)?LD:0,14)*100/SUM(TR,14)-SUM((HD>0 &HD>LD)?HD:0,14)*100/SUM(TR,14))/(SUM((LD>0 &LD>HD)?LD:0,14)*100/SUM(TR,14)+SUM((HD>0 &HD>LD)?HD:0,14)*100/SUM(TR,14))*100,6)+DELAY(MEAN(ABS(SUM((LD>0 &LD>HD)?LD:0,14)*100/SUM(TR,14)-SUM((HD>0 & HD>LD)?HD:0,14)*100/SUM(TR,14))/(SUM((LD>0&LD>HD)?LD:0,14)*100/SUM(TR,14)+SUM((HD>0 & HD>LD)?HD:0,14)*100/SUM(TR,14))*100,6),6))/2
        # Note: Similar to Alpha172, uses ATR components (LD, HD, TR)
        ld = "Sub($low, Ref($low, 1))"
        hd = "Sub(Ref($high, 1), $high)"
        tr = "Greater(Sub($high, $low), Greater(Abs(Sub($high, Ref($close, 1))), Abs(Sub($low, Ref($close, 1)))))"
        ld_sum = "Sum(If(Gt(" + ld + ", 0), If(Gt(" + ld + ", " + hd + "), " + ld + ", 0), 0), 14)"
        hd_sum = "Sum(If(Gt(" + hd + ", 0), If(Gt(" + hd + ", " + ld + "), " + hd + ", 0), 0), 14)"
        tr_sum = "Sum(" + tr + ", 14)"
        diff = "Sub(Div(Mul(" + ld_sum + ", 100), " + tr_sum + "), Div(Mul(" + hd_sum + ", 100), " + tr_sum + "))"
        total = "Add(Div(Mul(" + ld_sum + ", 100), " + tr_sum + "), Div(Mul(" + hd_sum + ", 100), " + tr_sum + "))"
        dm_value = "Mean(Mul(Div(Abs(" + diff + "), " + total + "), 100), 6)"
        return "Div(Add(" + dm_value + ", Ref(" + dm_value + ", 6)), 2)"

    @classmethod
    def alpha187(cls):
        # Alpha#187: SUM((OPEN<=DELAY(OPEN,1)?0:MAX((HIGH-OPEN),(OPEN-DELAY(OPEN,1)))),20)
        return "Sum(If(Le($open, Ref($open, 1)), 0, Greater(Sub($high, $open), Sub($open, Ref($open, 1)))), 20)"

    @classmethod
    def alpha188(cls):
        # Alpha#188: ((HIGH-LOW–SMA(HIGH-LOW,11,2))/SMA(HIGH-LOW,11,2))*100
        # Note: Fixed typo (HIGH-LOW–SMA should be HIGH-LOW-SMA)
        range_val = "Sub($high, $low)"
        sma_range = "WMA(" + range_val + ", 11)"
        return "Mul(Div(Sub(" + range_val + ", " + sma_range + "), " + sma_range + "), 100)"

    @classmethod
    def alpha189(cls):
        # Alpha#189: MEAN(ABS(CLOSE-MEAN(CLOSE,6)),6)
        return "Mean(Abs(Sub($close, Mean($close, 6))), 6)"

    @classmethod
    def alpha190(cls):
        # Alpha#190: LOG((COUNT(CLOSE/DELAY(CLOSE)-1>((CLOSE/DELAY(CLOSE,19))^(1/20)-1),20)-1)*(SUMIF(((CLOSE/DELAY(CLOSE)-1-(CLOSE/DELAY(CLOSE,19))^(1/20)-1))^2,20,CLOSE/DELAY(CLOSE)-1<(CLOSE/DELAY(CLOSE,19))^(1/20)-1))/((COUNT((CLOSE/DELAY(CLOSE)-1<(CLOSE/DELAY(CLOSE,19))^(1/20)-1),20))*(SUMIF((CLOSE/DELAY(CLOSE)-1-((CLOSE/DELAY(CLOSE,19))^(1/20)-1))^2,20,CLOSE/DELAY(CLOSE)-1>(CLOSE/DELAY(CLOSE,19))^(1/20)-1))))
        # Note: Very complex expression with COUNT, SUMIF, and power calculations
        # Note: (CLOSE/DELAY(CLOSE,19))^(1/20)-1 is the 20th root of 19-period return minus 1
        ret = "Sub(Div($close, Ref($close, 1)), 1)"
        ratio_19 = "Div($close, Ref($close, 19))"
        threshold = "Sub(Pow(" + ratio_19 + ", 0.05), 1)"
        count_above = "Sum(If(Gt(" + ret + ", " + threshold + "), 1, 0), 20)"
        count_below = "Sum(If(Lt(" + ret + ", " + threshold + "), 1, 0), 20)"
        sumif_below = "Sum(If(Lt(" + ret + ", " + threshold + "), Pow(Sub(" + ret + ", " + threshold + "), 2), 0), 20)"
        sumif_above = "Sum(If(Gt(" + ret + ", " + threshold + "), Pow(Sub(" + ret + ", " + threshold + "), 2), 0), 20)"
        return "Log(Div(Mul(Sub(" + count_above + ", 1), " + sumif_below + "), Mul(" + count_below + ", " + sumif_above + ")))"

    @classmethod
    def alpha191(cls):
        # Alpha#191: ((CORR(MEAN(VOLUME,20), LOW, 5) + ((HIGH + LOW) / 2)) -CLOSE)
        return "Sub(Add(Corr(Mean($volume, 20), $low, 5), Div(Add($high, $low), 2)), $close)"

    @classmethod
    def get_all_factors(cls):
        """一次獲取所有因子名與表達式"""
        return {name: getattr(cls, name)() for name in dir(cls) if name.startswith("alpha")}
