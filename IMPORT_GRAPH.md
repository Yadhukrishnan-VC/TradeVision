# Technical Indicators Module — Import Graph

## Module Import Structure

```
apps/technical_analysis/
├── __init__.py                    # exports: IndicatorService, IndicatorRegistry
├── apps.py                        # TechnicalAnalysisConfig
├── models.py                      # IndicatorResult, IndicatorConfiguration, IndicatorSnapshot, OHLCVSnapshot
├── admin.py                       # IndicatorResultAdmin, IndicatorConfigAdmin
├── services.py                    # IndicatorService
├── repository.py                  # IndicatorRepository, IndicatorResultRepository
├── serializers.py                 # IndicatorResultSerializer, IndicatorConfigSerializer
├── views.py                       # IndicatorViewSet
├── urls.py                        # router registration
├── tasks.py                       # ComputeIndicatorsTask
├── indicators/
│   ├── __init__.py                # exports: IndicatorFactory, IndicatorRegistry, all indicators
│   ├── base.py                    # BaseIndicator, IndicatorConfig, IndicatorResult, IndicatorType
│   ├── registry.py                # IndicatorRegistry (singleton), register_indicator()
│   ├── exceptions.py              # IndicatorError, InsufficientDataError, InvalidParameterError
│   ├── factory.py                 # IndicatorFactory, IndicatorBuilder
│   ├── trend/
│   │   ├── __init__.py            # exports: SMA, EMA, MACD, ADX
│   │   ├── sma.py                 # SMA
│   │   ├── ema.py                 # EMA
│   │   ├── macd.py                # MACD, MACDResult
│   │   └── adx.py                 # ADX, ADXResult
│   ├── momentum/
│   │   ├── __init__.py            # exports: RSI, StochasticOscillator
│   │   ├── rsi.py                 # RSI, RSIResult
│   │   └── stochastic.py          # StochasticOscillator, StochasticResult
│   ├── volatility/
│   │   ├── __init__.py            # exports: BollingerBands, ATR
│   │   ├── bollinger.py           # BollingerBands, BollingerBandsResult
│   │   └── atr.py                 # ATR, ATRResult
│   └── volume/
│       ├── __init__.py            # exports: OBV, VWAP, VolumeProfile
│       ├── obv.py                 # OBV, OBVResult
│       ├── vwap.py                # VWAP, VWAPResult
│       └── volume_profile.py      # VolumeProfile, VolumeProfileResult, VolumeNode
└── tests/
    ├── __init__.py
    ├── factories.py               # FactoryBoy factories
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

## Import Details by File

### apps/technical_analysis/__init__.py
```python
from apps.technical_analysis.services import IndicatorService
from apps.technical_analysis.indicators import IndicatorRegistry, IndicatorFactory
__all__ = ["IndicatorService", "IndicatorRegistry", "IndicatorFactory"]
```

### apps/technical_analysis/apps.py
```python
from django.apps import AppConfig
class TechnicalAnalysisConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.technical_analysis"
    verbose_name = "Technical Analysis"
```

### apps/technical_analysis/models.py
```python
from core.models import BaseModel
from django.db import models
from django.conf import settings
from apps.technical_analysis.indicators.base import IndicatorType
from core.market_data.base_provider import OHLCVBar
```

### apps/technical_analysis/admin.py
```python
from django.contrib import admin
from apps.technical_analysis.models import IndicatorResult, IndicatorConfiguration, IndicatorSnapshot
```

### apps/technical_analysis/services.py
```python
from core.repository import BaseRepository
from apps.technical_analysis.repository import IndicatorRepository, IndicatorResultRepository
from apps.technical_analysis.indicators import IndicatorFactory, IndicatorRegistry
from apps.technical_analysis.indicators.base import IndicatorConfig, IndicatorResult, IndicatorType
from core.market_data.base_provider import OHLCVBar
from core.utils import get_now
from decimal import Decimal
from datetime import datetime
from typing import Sequence
import logging
```

### apps/technical_analysis/repository.py
```python
from core.repository import BaseRepository
from apps.technical_analysis.models import IndicatorResult, IndicatorConfiguration
from apps.technical_analysis.indicators.base import IndicatorResult as IndicatorResultDTO, IndicatorType
from core.utils import get_now
from datetime import datetime
from typing import Sequence
import uuid
```

### apps/technical_analysis/serializers.py
```python
from rest_framework import serializers
from apps.technical_analysis.models import IndicatorResult, IndicatorConfiguration
from apps.technical_analysis.indicators.base import IndicatorType
```

### apps/technical_analysis/views.py
```python
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from apps.technical_analysis.serializers import IndicatorResultSerializer, IndicatorConfigSerializer
from apps.technical_analysis.services import IndicatorService
from apps.technical_analysis.indicators.base import IndicatorType
```

### apps/technical_analysis/tasks.py
```python
from core.tasks import BaseTask
from apps.technical_analysis.services import IndicatorService
from apps.technical_analysis.indicators.base import IndicatorType
from core.events import EventBus, EventType
from core.utils import get_now
import logging
```

### apps/technical_analysis/indicators/__init__.py
```python
from apps.technical_analysis.indicators.base import (
    BaseIndicator,
    IndicatorConfig,
    IndicatorResult,
    IndicatorType,
)
from apps.technical_analysis.indicators.registry import IndicatorRegistry, register_indicator
from apps.technical_analysis.indicators.factory import IndicatorFactory, IndicatorBuilder
from apps.technical_analysis.indicators.trend import SMA, EMA, MACD, ADX
from apps.technical_analysis.indicators.momentum import RSI, StochasticOscillator
from apps.technical_analysis.indicators.volatility import BollingerBands, ATR
from apps.technical_analysis.indicators.volume import OBV, VWAP, VolumeProfile
__all__ = [
    "BaseIndicator", "IndicatorConfig", "IndicatorResult", "IndicatorType",
    "IndicatorRegistry", "register_indicator",
    "IndicatorFactory", "IndicatorBuilder",
    "SMA", "EMA", "MACD", "ADX",
    "RSI", "StochasticOscillator",
    "BollingerBands", "ATR",
    "OBV", "VWAP", "VolumeProfile",
]
```

### apps/technical_analysis/indicators/base.py
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar, Generic, TypeVar
from enum import Enum
import uuid
```

### apps/technical_analysis/indicators/registry.py
```python
from apps.technical_analysis.indicators.base import BaseIndicator, IndicatorType, IndicatorConfig
from typing import ClassVar
import threading
import logging
```

### apps/technical_analysis/indicators/factory.py
```python
from apps.technical_analysis.indicators.registry import IndicatorRegistry
from apps.technical_analysis.indicators.base import IndicatorConfig, IndicatorType, BaseIndicator
from apps.technical_analysis.indicators.exceptions import IndicatorError
from typing import Any
import logging
```

### apps/technical_analysis/indicators/exceptions.py
```python
from core.exceptions import TradeVisionError
```

### apps/technical_analysis/indicators/trend/sma.py
```python
from apps.technical_analysis.indicators.base import BaseIndicator, IndicatorConfig, IndicatorResult, IndicatorType
from core.market_data.base_provider import OHLCVBar
from decimal import Decimal
from typing import Sequence
```

### apps/technical_analysis/indicators/trend/ema.py
```python
from apps.technical_analysis.indicators.base import BaseIndicator, IndicatorConfig, IndicatorResult, IndicatorType
from core.market_data.base_provider import OHLCVBar
from decimal import Decimal
from typing import Sequence
```

### apps/technical_analysis/indicators/trend/macd.py
```python
from apps.technical_analysis.indicators.base import BaseIndicator, IndicatorConfig, IndicatorResult, IndicatorType
from apps.technical_analysis.indicators.trend.ema import EMA
from core.market_data.base_provider import OHLCVBar
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence
```

### apps/technical_analysis/indicators/trend/adx.py
```python
from apps.technical_analysis.indicators.base import BaseIndicator, IndicatorConfig, IndicatorResult, IndicatorType
from core.market_data.base_provider import OHLCVBar
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence
```

### apps/technical_analysis/indicators/momentum/rsi.py
```python
from apps.technical_analysis.indicators.base import BaseIndicator, IndicatorConfig, IndicatorResult, IndicatorType
from core.market_data.base_provider import OHLCVBar
from decimal import Decimal
from typing import Sequence
```

### apps/technical_analysis/indicators/momentum/stochastic.py
```python
from apps.technical_analysis.indicators.base import BaseIndicator, IndicatorConfig, IndicatorResult, IndicatorType
from core.market_data.base_provider import OHLCVBar
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence
```

### apps/technical_analysis/indicators/volatility/bollinger.py
```python
from apps.technical_analysis.indicators.base import BaseIndicator, IndicatorConfig, IndicatorResult, IndicatorType
from apps.technical_analysis.indicators.trend.sma import SMA
from core.market_data.base_provider import OHLCVBar
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence
```

### apps/technical_analysis/indicators/volatility/atr.py
```python
from apps.technical_analysis.indicators.base import BaseIndicator, IndicatorConfig, IndicatorResult, IndicatorType
from core.market_data.base_provider import OHLCVBar
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence
```

### apps/technical_analysis/indicators/volume/obv.py
```python
from apps.technical_analysis.indicators.base import BaseIndicator, IndicatorConfig, IndicatorResult, IndicatorType
from core.market_data.base_provider import OHLCVBar
from decimal import Decimal
from typing import Sequence
```

### apps/technical_analysis/indicators/volume/vwap.py
```python
from apps.technical_analysis.indicators.base import BaseIndicator, IndicatorConfig, IndicatorResult, IndicatorType
from core.market_data.base_provider import OHLCVBar
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence
```

### apps/technical_analysis/indicators/volume/volume_profile.py
```python
from apps.technical_analysis.indicators.base import BaseIndicator, IndicatorConfig, IndicatorResult, IndicatorType
from core.market_data.base_provider import OHLCVBar
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence
```

### apps/technical_analysis/tests/factories.py
```python
import factory
from factory.django import DjangoModelFactory
from apps.technical_analysis.models import IndicatorResult, IndicatorConfiguration, IndicatorSnapshot
from apps.technical_analysis.indicators.base import IndicatorType, IndicatorResult as IndicatorResultDTO
from core.market_data.base_provider import OHLCVBar
from decimal import Decimal
from datetime import datetime, timezone
import uuid
```

### apps/technical_analysis/tests/test_indicators/test_sma.py
```python
import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from core.market_data.base_provider import OHLCVBar
from apps.technical_analysis.indicators.trend.sma import SMA
from apps.technical_analysis.indicators.base import IndicatorConfig
```

(Similar pattern for all other indicator test files)

## Forbidden Import Patterns

```
❌ from apps.technical_analysis.indicators.trend import * (wildcard)
❌ from apps.technical_analysis.services import * in indicators/
❌ from apps.technical_analysis.tasks import * in indicators/
❌ from django.db import models in indicators/
❌ from celery import * in indicators/
❌ Circular imports between indicator modules
✅ from apps.technical_analysis.indicators.trend.sma import SMA (explicit)
✅ from apps.technical_analysis.indicators.base import BaseIndicator
✅ from core.market_data.base_provider import OHLCVBar
✅ Relative imports within indicators/ package
```