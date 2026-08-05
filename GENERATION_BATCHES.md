# Technical Indicators Module — Generation Batches

## Batch 1: Core Infrastructure (5 files)
**Dependencies**: None (only core.*, stdlib)
**Order**: Sequential within batch

1. `apps/technical_analysis/indicators/exceptions.py` — Custom exceptions
2. `apps/technical_analysis/indicators/base.py` — BaseIndicator, IndicatorConfig, IndicatorResult, IndicatorType
3. `apps/technical_analysis/indicators/registry.py` — IndicatorRegistry singleton
4. `apps/technical_analysis/indicators/factory.py` — IndicatorFactory, IndicatorBuilder
5. `apps/technical_analysis/indicators/__init__.py` — Package exports (updated after each indicator batch)

---

## Batch 2: Trend Indicators (4 files + 1 init)
**Dependencies**: Batch 1, `core.market_data.base_provider.OHLCVBar`
**Order**: SMA → EMA → MACD → ADX

1. `apps/technical_analysis/indicators/trend/__init__.py`
2. `apps/technical_analysis/indicators/trend/sma.py`
3. `apps/technical_analysis/indicators/trend/ema.py`
4. `apps/technical_analysis/indicators/trend/macd.py` (uses EMA internally)
5. `apps/technical_analysis/indicators/trend/adx.py`

---

## Batch 3: Momentum Indicators (2 files + 1 init)
**Dependencies**: Batch 1, `core.market_data.base_provider.OHLCVBar`

1. `apps/technical_analysis/indicators/momentum/__init__.py`
2. `apps/technical_analysis/indicators/momentum/rsi.py`
3. `apps/technical_analysis/indicators/momentum/stochastic.py`

---

## Batch 4: Volatility Indicators (2 files + 1 init)
**Dependencies**: Batch 1, Batch 2 (SMA for Bollinger), `core.market_data.base_provider.OHLCVBar`

1. `apps/technical_analysis/indicators/volatility/__init__.py`
2. `apps/technical_analysis/indicators/volatility/bollinger.py` (uses SMA internally)
3. `apps/technical_analysis/indicators/volatility/atr.py`

---

## Batch 5: Volume Indicators (3 files + 1 init)
**Dependencies**: Batch 1, `core.market_data.base_provider.OHLCVBar`

1. `apps/technical_analysis/indicators/volume/__init__.py`
2. `apps/technical_analysis/indicators/volume/obv.py`
3. `apps/technical_analysis/indicators/volume/vwap.py`
4. `apps/technical_analysis/indicators/volume/volume_profile.py`

---

## Batch 6: Django App Models & Admin (2 files)
**Dependencies**: Batches 1-5, `core.models.BaseModel`, `core.protocols.Identifiable`
**Order**: Models → Admin

1. `apps/technical_analysis/models.py`
2. `apps/technical_analysis/admin.py`

---

## Batch 7: Repository & Service Layer (2 files)
**Dependencies**: Batch 6, `core.repository.BaseRepository`, `core.events.EventBus`

1. `apps/technical_analysis/repository.py`
2. `apps/technical_analysis/services.py`

---

## Batch 8: API Layer (3 files)
**Dependencies**: Batch 7, `rest_framework`, `django_filters`

1. `apps/technical_analysis/serializers.py`
2. `apps/technical_analysis/views.py`
3. `apps/technical_analysis/urls.py`

---

## Batch 9: Celery Tasks & App Config (2 files)
**Dependencies**: Batch 7, `core.tasks.BaseTask`, `core.constants.TaskName`, `core.constants.QueueName`

1. `apps/technical_analysis/tasks.py`
2. `apps/technical_analysis/apps.py` (update ready())

---

## Batch 10: Test Infrastructure (1 file)
**Dependencies**: All batches, `factory_boy`, `pytest`

1. `apps/technical_analysis/tests/factories.py`

---

## Batch 11: Indicator Unit Tests (10 files)
**Dependencies**: Batch 10, indicator implementations

| File | Depends On |
|------|------------|
| `test_indicators/test_sma.py` | Batch 2 |
| `test_indicators/test_ema.py` | Batch 2 |
| `test_indicators/test_rsi.py` | Batch 3 |
| `test_indicators/test_macd.py` | Batch 2 |
| `test_indicators/test_bollinger.py` | Batch 4 |
| `test_indicators/test_atr.py` | Batch 4 |
| `test_indicators/test_adx.py` | Batch 2 |
| `test_indicators/test_stochastic.py` | Batch 3 |
| `test_indicators/test_obv.py` | Batch 5 |
| `test_indicators/test_vwap.py` | Batch 5 |
| `test_indicators/test_volume_profile.py` | Batch 5 |

---

## Batch 12: Integration Tests (5 files)
**Dependencies**: Batches 6-9, Batch 10

| File | Tests |
|------|-------|
| `test_factory.py` | IndicatorFactory, IndicatorBuilder, registry |
| `test_registry.py` | IndicatorRegistry singleton, registration |
| `test_service.py` | IndicatorService compute, cache, query |
| `test_repository.py` | Repository CRUD, query methods |
| `test_models.py` | Model fields, constraints, managers |
| `test_api.py` | ViewSet endpoints, filters, pagination |
| `test_tasks.py` | ComputeIndicatorsTask execution |

---

## Batch 13: Configuration & Migration (2 files - generated)

1. `backend/config/settings/base.py` — Add to `LOCAL_APPS` (manual edit)
2. `backend/apps/technical_analysis/migrations/0001_initial.py` — Run `makemigrations`

---

## Validation Commands After Each Batch

```bash
# After Batch 1-5 (indicators only - no Django needed)
cd /home/yadhukrishnan/Music/TradeVision/backend
python -c "from apps.technical_analysis.indicators import SMA, EMA, RSI, MACD, BollingerBands, ATR, ADX, StochasticOscillator, OBV, VWAP, VolumeProfile; print('Imports OK')"

# After Batch 6-9 (full Django)
cd /home/yadhukrishnan/Music/TradeVision/backend
python manage.py check
python manage.py makemigrations technical_analysis --dry-run

# After Batch 10-12 (tests)
cd /home/yadhukrishnan/Music/TradeVision/backend
pytest apps/technical_analysis/tests/ -v --tb=short

# Lint & Type Check
ruff check apps/technical_analysis/
mypy apps/technical_analysis/
black --check apps/technical_analysis/
```

---

## Parallel Execution Notes

| Can Run Parallel | Must Run Sequential |
|------------------|---------------------|
| Batch 2, 3, 4, 5 (different indicator categories) | Batch 1 before 2-5 |
| Batch 11 test files (all independent) | Batch 6 before 7, 8, 9 |
| Batch 12 test files (mostly independent) | Batch 10 before 11, 12 |

---

## Estimated Effort

| Batch | Files | Est. Time |
|-------|-------|-----------|
| 1 | 5 | 30 min |
| 2 | 5 | 45 min |
| 3 | 3 | 30 min |
| 4 | 3 | 30 min |
| 5 | 4 | 40 min |
| 6 | 2 | 25 min |
| 7 | 2 | 30 min |
| 8 | 3 | 25 min |
| 9 | 2 | 20 min |
| 10 | 1 | 30 min |
| 11 | 11 | 60 min |
| 12 | 7 | 45 min |
| **Total** | **48** | **~7 hours** |