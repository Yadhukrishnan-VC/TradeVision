# Technical Indicators Module — File Inventory

## New Files to Create (53 files)

### Core Indicator Modules (14 files)

| File | Lines (est.) | Purpose |
|------|--------------|---------|
| `apps/technical_analysis/indicators/__init__.py` | 30 | Package exports |
| `apps/technical_analysis/indicators/base.py` | 120 | BaseIndicator abstract class, IndicatorConfig, IndicatorResult, IndicatorType enum |
| `apps/technical_analysis/indicators/registry.py` | 80 | IndicatorRegistry singleton, register_indicator decorator |
| `apps/technical_analysis/indicators/factory.py` | 80 | IndicatorFactory, IndicatorBuilder |
| `apps/technical_analysis/indicators/exceptions.py` | 40 | IndicatorError, InsufficientDataError, InvalidParameterError |

### Trend Indicators (4 files)

| File | Lines (est.) | Purpose |
|------|--------------|---------|
| `apps/technical_analysis/indicators/trend/__init__.py` | 15 | Exports: SMA, EMA, MACD, ADX |
| `apps/technical_analysis/indicators/trend/sma.py` | 80 | Simple Moving Average |
| `apps/technical_analysis/indicators/trend/ema.py` | 80 | Exponential Moving Average |
| `apps/technical_analysis/indicators/trend/macd.py` | 100 | MACD with signal line & histogram |
| `apps/technical_analysis/indicators/trend/adx.py` | 120 | Average Directional Index (+DI, -DI, ADX) |

### Momentum Indicators (2 files)

| File | Lines (est.) | Purpose |
|------|--------------|---------|
| `apps/technical_analysis/indicators/momentum/__init__.py` | 15 | Exports: RSI, StochasticOscillator |
| `apps/technical_analysis/indicators/momentum/rsi.py` | 90 | Relative Strength Index |
| `apps/technical_analysis/indicators/momentum/stochastic.py` | 100 | Stochastic Oscillator (%K, %D) |

### Volatility Indicators (2 files)

| File | Lines (est.) | Purpose |
|------|--------------|---------|
| `apps/technical_analysis/indicators/volatility/__init__.py` | 15 | Exports: BollingerBands, ATR |
| `apps/technical_analysis/indicators/volatility/bollinger.py` | 100 | Bollinger Bands (middle, upper, lower, bandwidth, %B) |
| `apps/technical_analysis/indicators/volatility/atr.py` | 90 | Average True Range |

### Volume Indicators (3 files)

| File | Lines (est.) | Purpose |
|------|--------------|---------|
| `apps/technical_analysis/indicators/volume/__init__.py` | 15 | Exports: OBV, VWAP, VolumeProfile |
| `apps/technical_analysis/indicators/volume/obv.py` | 80 | On-Balance Volume |
| `apps/technical_analysis/indicators/volume/vwap.py` | 90 | Volume Weighted Average Price |
| `apps/technical_analysis/indicators/volume/volume_profile.py` | 130 | Volume Profile (POC, VAH, VAL, nodes) |

### Django App Layer (8 files)

| File | Lines (est.) | Purpose |
|------|--------------|---------|
| `apps/technical_analysis/__init__.py` | 20 | App exports |
| `apps/technical_analysis/apps.py` | 25 | AppConfig |
| `apps/technical_analysis/models.py` | 200 | IndicatorResult, IndicatorConfiguration, IndicatorSnapshot, OHLCVSnapshot |
| `apps/technical_analysis/admin.py` | 80 | Django admin registration |
| `apps/technical_analysis/services.py` | 180 | IndicatorService (compute, query, cache) |
| `apps/technical_analysis/repository.py` | 120 | IndicatorRepository, IndicatorResultRepository |
| `apps/technical_analysis/serializers.py` | 100 | DRF serializers |
| `apps/technical_analysis/views.py` | 120 | IndicatorViewSet |
| `apps/technical_analysis/urls.py` | 30 | Router registration |
| `apps/technical_analysis/tasks.py` | 100 | ComputeIndicatorsTask (Celery) |

### Tests (22 files)

| File | Lines (est.) | Purpose |
|------|--------------|---------|
| `apps/technical_analysis/tests/__init__.py` | 5 | Test package |
| `apps/technical_analysis/tests/factories.py` | 150 | FactoryBoy factories |
| `apps/technical_analysis/tests/test_indicators/__init__.py` | 5 | Indicator test package |
| `apps/technical_analysis/tests/test_indicators/test_sma.py` | 80 | SMA unit tests |
| `apps/technical_analysis/tests/test_indicators/test_ema.py` | 80 | EMA unit tests |
| `apps/technical_analysis/tests/test_indicators/test_rsi.py` | 90 | RSI unit tests |
| `apps/technical_analysis/tests/test_indicators/test_macd.py` | 100 | MACD unit tests |
| `apps/technical_analysis/tests/test_indicators/test_bollinger.py` | 100 | Bollinger Bands tests |
| `apps/technical_analysis/tests/test_indicators/test_atr.py` | 80 | ATR unit tests |
| `apps/technical_analysis/tests/test_indicators/test_adx.py` | 100 | ADX unit tests |
| `apps/technical_analysis/tests/test_indicators/test_stochastic.py` | 90 | Stochastic tests |
| `apps/technical_analysis/tests/test_indicators/test_obv.py` | 80 | OBV unit tests |
| `apps/technical_analysis/tests/test_indicators/test_vwap.py` | 90 | VWAP unit tests |
| `apps/technical_analysis/tests/test_indicators/test_volume_profile.py` | 100 | Volume Profile tests |
| `apps/technical_analysis/tests/test_factory.py` | 80 | Factory/Builder tests |
| `apps/technical_analysis/tests/test_registry.py` | 60 | Registry tests |
| `apps/technical_analysis/tests/test_service.py` | 120 | Service layer tests |
| `apps/technical_analysis/tests/test_repository.py` | 100 | Repository tests |
| `apps/technical_analysis/tests/test_models.py` | 100 | Model tests |
| `apps/technical_analysis/tests/test_api.py` | 120 | API endpoint tests |
| `apps/technical_analysis/tests/test_tasks.py` | 80 | Celery task tests |

## Files to Modify (3 files)

| File | Change |
|------|--------|
| `backend/config/settings/base.py` | Add `apps.technical_analysis` to `LOCAL_APPS` |
| `backend/apps/technical_analysis/migrations/0001_initial.py` | Auto-generated after makemigrations |
| `backend/config/celery.py` | Register `ComputeIndicatorsTask` (if task auto-discovery not used) |

## Total Estimated Lines: ~3,500 lines

## Directory Structure After Creation

```
backend/apps/technical_analysis/
├── __init__.py
├── apps.py
├── models.py
├── admin.py
├── services.py
├── repository.py
├── serializers.py
├── views.py
├── urls.py
├── tasks.py
├── indicators/
│   ├── __init__.py
│   ├── base.py
│   ├── registry.py
│   ├── factory.py
│   ├── exceptions.py
│   ├── trend/
│   │   ├── __init__.py
│   │   ├── sma.py
│   │   ├── ema.py
│   │   ├── macd.py
│   │   └── adx.py
│   ├── momentum/
│   │   ├── __init__.py
│   │   ├── rsi.py
│   │   └── stochastic.py
│   ├── volatility/
│   │   ├── __init__.py
│   │   ├── bollinger.py
│   │   └── atr.py
│   └── volume/
│       ├── __init__.py
│       ├── obv.py
│       ├── vwap.py
│       └── volume_profile.py
├── migrations/
│   └── __init__.py
└── tests/
    ├── __init__.py
    ├── factories.py
    ├── test_indicators/
    │   ├── __init__.py
    │   ├── test_sma.py
    │   ├── test_ema.py
    │   ├── test_rsi.py
    │   ├── test_macd.py
    │   ├── test_bollinger.py
    │   ├── test_atr.py
    │   ├── test_adx.py
    │   ├── test_stochastic.py
    │   ├── test_obv.py
    │   ├── test_vwap.py
    │   └── test_volume_profile.py
    ├── test_factory.py
    ├── test_registry.py
    ├── test_service.py
    ├── test_repository.py
    ├── test_models.py
    ├── test_api.py
    └── test_tasks.py
```