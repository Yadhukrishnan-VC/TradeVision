# ADR-015: DeepSeek AI Provider

**Status:** APPROVED — Implementation Specification  
**Date:** 2026-07-26  
**Owner:** Principal AI Architect  
**Depends on:** ADR-014

## Context

The AI provider interface (ADR-003) supports Gemini, OpenAI, Claude, and Ollama. DeepSeek offers strong analytical capabilities at competitive pricing, making it ideal for breakout/breakdown pattern recognition and regime analysis.

## Decision

Add `DeepSeekProvider` as a fifth AI provider implementation following the same Phase 0 pattern as `GeminiProvider`:

### Provider Characteristics

| Aspect | Decision |
|---|---|
| SDK | `httpx` (same as Claude will use) |
| Auth | API key via HTTP header `Authorization: Bearer {key}` |
| Endpoint | `POST /v1/chat/completions` (OpenAI-compatible) |
| Validation | `GET /v1/models` |
| Phase 0 Scope | Auth + health + connection validation only. `complete()` raises `NotImplementedError` |

### Error Mapping

| Condition | Exception |
|---|---|
| Empty `api_key` at construction | `AIAuthenticationError` |
| `httpx.ConnectError` / DNS failure | `AIConnectionError` |
| HTTP 401/403 | `AIAuthenticationError` |
| HTTP 429 | `AIRateLimitError` |
| `httpx.TimeoutException` | `AITimeoutError` |
| Any other non-2xx | `AIProviderError` |

### Routing

DeepSeek becomes the preferred provider for:
- `BREAKOUT` / `BREAKDOWN` events
- `VOLATILE` market regimes
- `GAP_MOVEMENT` events
- `CIRCUIT_BREAKER` events
- `INSTITUTIONAL_ACTIVITY` events

## Consequences

- Five providers available for model routing (Batch E)
- DeepSeek occupies the mid-tier cost position between Gemini (cheap) and Claude (expensive)
- `AIProviderFactory._create_provider()` gains a sixth branch (matching the pattern of the existing five)

## Configuration

| Setting | Default |
|---|---|
| `DEEPSEEK_API_KEY` | `""` |
| `DEEPSEEK_MODEL` | `"deepseek-chat"` |
| `DEEPSEEK_BASE_URL` | `"https://api.deepseek.com"` |
