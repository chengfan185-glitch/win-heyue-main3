# Win Rate Enhancement Filters

## 概述 (Overview)

完整的交易质量过滤系统，实现 6 大胜率提升机制。

Complete trading quality filter system implementing 6 win rate enhancement mechanisms.

## 核心模块 (Core Modules)

### 1. 信号一致性过滤 (Signal Consistency Filter) ⭐
`core/filters/signal_consistency.py`

**问题**: 单时刻判断容易受市场噪音干扰

**解决**: 要求信号在连续 N 根 K 线保持一致才开仓

**效果**:
- ❌ 砍掉大量"抖动假信号"
- ✅ 胜率提升 +5%~10%
- ❌ 交易频率下降（这是好事）

**配置**:
```python
from core.filters import SignalConsistencyFilter

filter = SignalConsistencyFilter(
    consistency_window=3,      # 检查最近 3 根 K 线
    min_consistency_ratio=0.8, # 至少 80% 一致
    enable_filter=True
)

# 检查信号
allowed, reason = filter.check_signal_consistency(
    symbol="BTCUSDT",
    signal="LONG",
    timestamp=time.time()
)

if allowed:
    # 执行交易
    execute_trade()
else:
    print(f"Signal blocked: {reason}")
```

### 2. 失败模式黑名单 (Failure Mode Blacklist) ⭐⭐
`core/filters/failure_blacklist.py`

**问题**: 某些 (策略 + 市场状态) 组合持续亏损

**解决**: 自动追踪并禁止低胜率/负 EV 组合

**这是职业量化必备**，但 90% 散户没做

**效果**:
- 最快、最干净的胜率提升方式
- 自动屏蔽已知的失败场景

**示例黑名单**:
```
strategy_X + VOLATILE market + high_volatility
→ 胜率 < 40% → ⛔ 自动禁止

strategy_Y + RANGING market + low_volume  
→ EV < -$50 → ⛔ 自动禁止
```

**配置**:
```python
from core.filters import FailureModeBlacklist

blacklist = FailureModeBlacklist(
    min_trades_for_analysis=10,
    blacklist_win_rate_threshold=0.40,  # 胜率 < 40% 禁止
    blacklist_ev_threshold=-50.0        # EV < -$50 禁止
)

# 交易前检查
allowed, reason = blacklist.check_combination(
    strategy_id="my_strategy",
    market_regime="VOLATILE",
    volatility=0.045
)

# 交易后记录结果
blacklist.record_trade_result(
    strategy_id="my_strategy",
    market_regime="VOLATILE",
    volatility=0.045,
    pnl=-25.50,
    win=False
)
```

### 3. 市场状态感知出场 (Market-Aware Exits) ⭐⭐⭐
`core/filters/market_aware_exits.py`

**问题**: 固定 TP/SL 不适应市场变化

**解决**: 根据市场状态动态调整 TP/SL

**策略**:
- **TRENDING**: 放大 TP，缩小 SL（让盈利跑）
- **RANGING**: 小 TP + 快 SL（快进快出）
- **VOLATILE**: 极窄仓位或不进场

**效果**: 不一定提高胜率，但显著提高净收益

**配置**:
```python
from core.filters import MarketAwareExits

exits = MarketAwareExits()

# 计算自适应出场位
exit_levels = exits.calculate_exit_levels(
    entry_price=50000.0,
    side="LONG",
    market_regime="TRENDING_UP",
    base_tp_pct=0.04,  # 基础 4% TP
    base_sl_pct=0.02,  # 基础 2% SL
    volatility=0.025
)

print(f"TP: {exit_levels['tp_price']}")
print(f"SL: {exit_levels['sl_price']}")
print(f"R:R: {exit_levels['risk_reward_ratio']:.2f}")
print(f"Use trailing: {exit_levels['use_trailing']}")
```

**各状态策略**:
```
TRENDING_UP/DOWN:
  TP × 1.5, SL × 0.8
  使用追踪止损 (1.5%)
  策略: 让趋势跑，快速止损

RANGING:
  TP × 0.7, SL × 1.0
  不用追踪止损
  策略: 快速获利了结

VOLATILE:
  TP × 0.6, SL × 0.7
  不用追踪止损
  策略: 极窄止损或避免

QUIET:
  TP × 1.0, SL × 1.2
  使用追踪止损 (1%)
  策略: 放宽止损减少噪音
```

### 4. 交易质量评分 (Trade Quality Scorer) ⭐
`core/filters/trade_quality.py`

**核心理念**: 不是"能不能下单"，而是"值不值得下单"

**评分维度**:
1. 信号强度 (30%)
2. 市场状态匹配度 (25%)
3. 历史表现 (25%)
4. 风险回报比 (20%)

**策略**:
- 只允许评分 ≥ 阈值的交易进入实盘
- 低评分继续纸上跑

**配置**:
```python
from core.filters import TradeQualityScorer

scorer = TradeQualityScorer(
    min_quality_score=60.0,  # 最低 60 分才允许
    enable_scoring=True
)

# 评估交易质量
score, allowed, components = scorer.score_trade(
    signal_confidence=0.75,
    market_regime="TRENDING_UP",
    strategy_type="trend_following",
    historical_win_rate=0.58,
    risk_reward_ratio=2.1
)

print(f"Quality Score: {score:.1f}/100")
print(f"Allowed: {allowed}")
print(f"Components: {components}")
```

### 5. 时间过滤器 (Time Filter) ⭐
`core/filters/time_filter.py`

**现实**: 市场在一天中不是每个时段都适合交易

**解决**: 按 UTC 时间段统计胜率，自动禁用低胜率时间段

**效果**:
- 很多系统从胜率 55% → 62%+
- 简单但有效

**配置**:
```python
from core.filters import TimeFilter

time_filter = TimeFilter(
    min_trades_per_hour=5,
    min_win_rate_threshold=0.45,  # 胜率 < 45% 禁止
    enable_filter=True
)

# 检查当前时间
allowed, reason = time_filter.check_time_allowed()

if allowed:
    execute_trade()
else:
    print(f"Time blocked: {reason}")

# 记录交易结果
time_filter.record_trade_result(
    timestamp=time.time(),
    pnl=125.50,
    win=True
)
```

### 6. 期望值优先 (Expected Value Focus)

**认知升级**: 从"胜率"到"期望值 (EV)"

**现实**:
- 胜率 55% + 盈亏比 1.8 = 健康策略
- 胜率 70% 但滑点大、容量低 = 不可持续
- 中低频合约策略：55%–62% 是健康区间
- 超过 65% 往往过拟合

**标准**:
```python
Expected Value (EV) = (Win Rate × Avg Win) - ((1 - Win Rate) × Avg Loss)

健康策略示例:
  胜率: 58%
  盈亏比: 1.8
  回撤可控
  → 这已经是"可带资金"的策略
```

**计算 EV**:
```python
from core.filters.market_aware_exits import MarketAwareExits

exits = MarketAwareExits()

ev = exits.calculate_expected_value(
    win_rate=0.58,
    avg_win=150.0,
    avg_loss=85.0,
    tp_pct=0.04,
    sl_pct=0.02
)

print(f"Expected Value: ${ev:.2f} per trade")
```

## 完整集成示例 (Complete Integration)

```python
from core.filters import (
    SignalConsistencyFilter,
    FailureModeBlacklist,
    TradeQualityScorer,
    TimeFilter,
    MarketAwareExits
)
from core.backtest.market_state import MarketStateAnalyzer

# 初始化所有过滤器
signal_filter = SignalConsistencyFilter(consistency_window=3)
blacklist = FailureModeBlacklist()
quality_scorer = TradeQualityScorer(min_quality_score=60.0)
time_filter = TimeFilter()
exits = MarketAwareExits()
market_analyzer = MarketStateAnalyzer()

# 交易前检查流程
def should_execute_trade(
    symbol: str,
    signal: str,
    signal_confidence: float,
    strategy_id: str,
    klines: list
):
    """完整的交易前检查流程"""
    
    # 1. 分析市场状态
    market_state = market_analyzer.analyze(klines, symbol)
    market_state.classify_regime()
    
    # 2. 信号一致性检查
    allowed, reason = signal_filter.check_signal_consistency(
        symbol, signal, time.time()
    )
    if not allowed:
        print(f"❌ Signal consistency: {reason}")
        return False, None
    
    # 3. 时间过滤
    allowed, reason = time_filter.check_time_allowed()
    if not allowed:
        print(f"❌ Time filter: {reason}")
        return False, None
    
    # 4. 失败模式黑名单
    allowed, reason = blacklist.check_combination(
        strategy_id=strategy_id,
        market_regime=market_state.regime.value,
        volatility=market_state.volatility_24h
    )
    if not allowed:
        print(f"⛔ Blacklist: {reason}")
        return False, None
    
    # 5. 交易质量评分
    score, allowed, components = quality_scorer.score_trade(
        signal_confidence=signal_confidence,
        market_regime=market_state.regime.value,
        strategy_type="trend_following",
        historical_win_rate=0.58,
        risk_reward_ratio=2.0
    )
    if not allowed:
        print(f"❌ Quality score too low: {score:.1f}/100")
        return False, None
    
    # 6. 计算自适应出场
    price = market_state.price
    exit_levels = exits.calculate_exit_levels(
        entry_price=price,
        side=signal,
        market_regime=market_state.regime.value,
        volatility=market_state.volatility_24h
    )
    
    print(f"✅ All filters passed!")
    print(f"   Quality Score: {score:.1f}/100")
    print(f"   Market: {market_state.regime.value}")
    print(f"   TP: {exit_levels['tp_price']:.2f}")
    print(f"   SL: {exit_levels['sl_price']:.2f}")
    print(f"   R:R: {exit_levels['risk_reward_ratio']:.2f}")
    
    return True, exit_levels

# 使用示例
allowed, exits = should_execute_trade(
    symbol="BTCUSDT",
    signal="LONG",
    signal_confidence=0.75,
    strategy_id="futures_trend_v1",
    klines=fetch_klines("BTCUSDT", 100)
)

if allowed:
    execute_trade_with_exits(exits)
```

## 性能影响 (Performance Impact)

**预期提升**:
```
基线策略胜率: 50%

+ 信号一致性过滤:    55% (+5%)
+ 失败模式黑名单:    58% (+3%)
+ 时间过滤:          62% (+4%)
+ 交易质量评分:      64% (+2%)

最终胜率: 60-65%
交易频率: -30% (质量优于数量)
净收益: +40-60% (更高 R:R + 更少亏损)
```

**注意**: 实际效果因策略而异，需在回测中验证

## 关键洞察 (Key Insights)

1. **质量 > 数量**: 少交易，交易质量高的
2. **自适应 > 固定**: 根据市场调整而非死板规则
3. **数据驱动**: 基于历史表现自动优化
4. **防御优先**: 先避免亏损，再追求盈利
5. **EV 导向**: 期望值为正才是可持续的

## 相关文档

- [futures_runner_v2.py](../pipeline/futures_runner_v2.py) - 主交易运行器
- [BACKTEST_WALKFORWARD.md](./BACKTEST_WALKFORWARD.md) - 回测框架
