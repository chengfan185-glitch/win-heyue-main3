# Backtest and Walk-Forward Validation Framework

## 概述 (Overview)

完整的「回测 + Walk-Forward 模块」，实现「纸上 → 实盘准入机制」，引入「策略 ID + 市场状态」管理。

Complete backtesting and walk-forward validation framework with paper-to-live admission gates, strategy ID tracking, and market state management.

## 核心组件 (Core Components)

### 1. 市场状态分类 (Market State Classification)
`core/backtest/market_state.py`

- **MarketRegime**: 市场状态枚举
  - `TRENDING_UP`: 上升趋势
  - `TRENDING_DOWN`: 下降趋势
  - `RANGING`: 震荡横盘
  - `VOLATILE`: 高波动
  - `QUIET`: 低波动
  - `UNKNOWN`: 未知/数据不足

- **MarketState**: 完整的市场状态数据结构
  - 价格变化 (1h, 4h, 24h)
  - 波动率指标
  - 成交量比率
  - 技术指标 (EMA, RSI)
  - 自动状态分类

### 2. 策略注册表 (Strategy Registry)
`core/backtest/strategy_registry.py`

- **StrategyMetrics**: 策略性能指标
  - 总交易数、胜率、盈亏比
  - Sharpe 比率、最大回撤
  - 回测/前进验证状态
  - 实盘批准状态

- **StrategyRegistry**: 策略管理注册中心
  - 注册和追踪策略版本
  - 记录性能指标
  - 批准/禁用实盘交易
  - 持久化到磁盘

### 3. 回测引擎 (Backtest Engine)
`core/backtest/backtest_engine.py`

- **BacktestEngine**: 历史数据回测
  - 逐K线模拟交易
  - 止损/止盈/追踪止损执行
  - 权益曲线追踪
  - 性能指标计算
  - 自动评估通过/失败

### 4. Walk-Forward 验证 (Walk-Forward Validation)
`core/backtest/walk_forward.py`

- **WalkForwardValidator**: 前进分析验证
  - 滚动时间窗口 (训练集/测试集)
  - 多窗口一致性检验
  - 过拟合检测
  - 性能退化分析

### 5. 准入门控 (Admission Gate)
`core/backtest/admission_gate.py`

- **AdmissionGate**: 纸上→实盘门禁
  - 多阶段验证要求
  - 市场状态兼容性检查
  - 批准/拒绝日志记录
  - 实盘启用/禁用控制

## 使用流程 (Usage Workflow)

### 完整验证流程 (Complete Validation)

```bash
# 1. 验证策略 (Validate strategy)
python tools/validate_strategy.py \
    --strategy-id my_futures_strategy \
    --version 1.0 \
    --symbol BTCUSDT \
    --data-limit 2000

# 2. 如果通过，启用实盘 (If passed, enable live)
python tools/validate_strategy.py \
    --strategy-id my_futures_strategy \
    --version 1.0 \
    --symbol BTCUSDT \
    --enable-live
```

### Python API 使用 (Python API Usage)

```python
from core.backtest import (
    BacktestEngine,
    WalkForwardValidator,
    StrategyRegistry,
    AdmissionGate
)

# 1. 定义策略函数
def my_strategy(bar, bar_index):
    price = bar['close']
    # ... your strategy logic ...
    
    if signal == 'buy':
        return 'LONG', {
            'size_usd': 200,
            'stop_loss': price * 0.98,
            'take_profit': price * 1.04
        }
    return 'HOLD', {}

# 2. 获取历史数据
data = fetch_historical_klines('BTCUSDT', limit=2000)

# 3. 回测
engine = BacktestEngine(initial_capital=10000)
backtest_result = engine.run(
    strategy_func=my_strategy,
    data=data,
    strategy_id='my_strategy',
    version='1.0'
)

print(f"Backtest PnL: {backtest_result.total_pnl}")
print(f"Win Rate: {backtest_result.win_rate:.2%}")
print(f"Passed: {backtest_result.passed}")

# 4. Walk-Forward 验证
validator = WalkForwardValidator()
wf_result = validator.validate(
    strategy_func=my_strategy,
    data=data,
    strategy_id='my_strategy',
    version='1.0'
)

print(f"Walk-Forward Consistency: {wf_result.consistency_score:.2%}")
print(f"Passed: {wf_result.passed}")

# 5. 注册策略并请求批准
registry = StrategyRegistry()
registry.register_strategy('my_strategy', '1.0')
registry.update_strategy_metrics('my_strategy', '1.0', backtest_result.trades)

gate = AdmissionGate()
approved = gate.request_approval(
    strategy_id='my_strategy',
    version='1.0',
    backtest_passed=backtest_result.passed,
    walkforward_passed=wf_result.passed
)

# 6. 启用实盘 (如果批准)
if approved:
    gate.enable_strategy('my_strategy', '1.0')
    print("✅ Strategy enabled for live trading!")
```

### 在 futures_runner_v2.py 中集成 (Integration in futures_runner_v2.py)

```python
from core.backtest import AdmissionGate, MarketState
from core.backtest.market_state import MarketStateAnalyzer

# 初始化
admission_gate = AdmissionGate()
market_analyzer = MarketStateAnalyzer()

# 交易前检查
strategy_id = "futures_trend_v1"
version = "1.0"

# 分析市场状态
klines = fetch_klines(symbol, limit=100)
market_state = market_analyzer.analyze(klines, symbol)

# 检查准入
allowed, reason = admission_gate.check_admission(
    strategy_id=strategy_id,
    version=version,
    market_state=market_state
)

if allowed:
    # 执行交易
    execute_trade(...)
else:
    print(f"Trading blocked: {reason}")
```

## 验证标准 (Validation Criteria)

### 回测通过标准 (Backtest Pass Criteria)
- 最少交易次数: 10
- 胜率: ≥ 45%
- 总盈亏: > 0
- 盈亏比: ≥ 1.1
- 最大回撤: < 30% 资金

### Walk-Forward 通过标准 (Walk-Forward Pass Criteria)
- 窗口通过率: ≥ 70%
- 性能退化: < 50% (测试期相比训练期)
- 测试期胜率: ≥ 40%
- 测试期盈利: > 0

### 实盘批准标准 (Live Approval Criteria)
- 总交易次数: ≥ 30
- 胜率: ≥ 52%
- 盈亏比: ≥ 1.2
- Sharpe 比率: ≥ 0.5
- 总盈亏: ≥ 0

## 文件结构 (File Structure)

```
core/backtest/
├── __init__.py                  # 模块初始化
├── market_state.py              # 市场状态分类
├── strategy_registry.py         # 策略注册管理
├── backtest_engine.py           # 回测引擎
├── walk_forward.py              # Walk-Forward 验证
└── admission_gate.py            # 准入门控

logs/
├── backtest_results/            # 回测结果
├── walkforward_results/         # Walk-Forward 结果
├── strategy_registry/           # 策略注册表
│   └── registry.json
└── admission_gate/              # 批准/拒绝日志
    ├── approvals_*.jsonl
    └── rejections_*.jsonl

tools/
└── validate_strategy.py         # 策略验证工具
```

## 关键特性 (Key Features)

1. **策略版本管理**: 每个策略有唯一 ID 和版本号
2. **完整性能追踪**: 从回测到实盘的全生命周期指标
3. **多阶段验证**: 回测 → Walk-Forward → 纸上交易 → 实盘
4. **市场状态感知**: 根据市场状态调整策略准入
5. **审计日志**: 所有批准/拒绝决策都有记录
6. **灵活配置**: 可自定义验证标准和要求

## 最佳实践 (Best Practices)

1. **先回测**: 在历史数据上验证策略基本逻辑
2. **再 Walk-Forward**: 确保策略在不同时期都稳健
3. **纸上交易**: 在实时数据上测试但不下真实订单
4. **小仓位实盘**: 批准后从小仓位开始实盘
5. **持续监控**: 实时监控策略表现，必要时禁用
6. **版本迭代**: 改进策略后重新验证新版本

## 相关文档 (Related Documentation)

- [QUICKSTART.md](../QUICKSTART.md) - 快速开始指南
- [PRODUCTION_GUIDE.md](../PRODUCTION_GUIDE.md) - 生产部署指南
- [futures_runner_v2.py](../pipeline/futures_runner_v2.py) - 主交易运行器
