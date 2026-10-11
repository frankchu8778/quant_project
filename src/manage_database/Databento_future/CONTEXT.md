# 美國期貨

CME 期貨與期貨選擇權的原始資料。研究主體是期貨（多商品趨勢跟蹤）；選擇權只作為期貨的補充資料。

## Language

**商品**:
一個期貨品種，例如 NQ、CL、GC。設定與存放都以商品為單位。
_Avoid_: product、標的、root symbol

**合約**:
一檔可交易的單一期貨或單一選擇權，例如 `NQM0`、`LOK0 C2500`。CME 會把到期合約的 instrument_id 重新分配給新合約，因此合約只能用 (instrument_id, raw_symbol) 唯一識別。
_Avoid_: instrument、標的

**選擇權系列**:
一組到期規則相同的選擇權合約，例如 LO（月選）、QN1（週選）。它屬於哪個商品，由其合約的標的期貨決定，而不是由系列代碼決定。
_Avoid_: option code、option product

**標的期貨**:
選擇權合約履約時交割的那一檔期貨合約，例如 `LOK0 C2500` 的標的期貨是 `CLK0`。
_Avoid_: underlying asset、現貨

**價差**:
由多個期貨合約組成、在交易所以單一代碼交易的組合，例如 `NQM0-NQU0` 或 `UD:` 開頭的自訂組合。它不是合約，與合約分開存放。選擇權的組合單（垂直價差等）不屬於本 context 的資料。
_Avoid_: spread、組合單

**交易日**:
CME 交易時段的歸屬日：前一個日曆日 17:00 CT 開始的時段，歸到下一個日曆日。與台股 context 的交易日（日曆日）不同。
_Avoid_: trade date、日期
