#!/usr/bin/env python
"""LIVE-BROKER-EXECUTION-1 Phase 1 — real sandbox.kite.trade smoke test.

Drives the REAL ``ZerodhaBroker`` adapter (no injected client, no mocks)
against ``https://sandbox.kite.trade`` and records every HTTP request/response
pair as evidence for docs/PHASE1_SANDBOX_SMOKE_TEST.md:

  1. exchange a login request_token for an access_token (generate_session)
  2. quote NSE:RELIANCE to price a resting LIMIT order (~2% below LTP so it
     rests OPEN instead of filling, per sandbox docs price-band guidance)
  3. place a LIMIT order through ``broker.place_order``
  4. place the SAME OrderPlacementRequest again (same correlation_id/tag) and
     prove idempotency: no second broker order is created (ADR-030 §4)
  5. fetch order status through ``broker.get_order_status``
  6. cancel through ``broker.cancel_order`` and confirm CANCELLED

Usage (from backend/ with a venv that has kiteconnect installed):

    .venv/bin/python ../scripts/kite_sandbox_smoke_test.py \
        --request-token <TOKEN_FROM_BROWSER_LOGIN_REDIRECT> \
        [--output /tmp/opencode/smoke_evidence.json]

Sandbox credentials are the public shared demo app (api_key=sandboxdemo) —
safe in plain text, no real money (ADR-030 §1).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django

django.setup()


def _wiretap(session) -> list[dict]:
    """Record every HTTP request/response pair flowing through the SDK."""
    transcript: list[dict] = []
    original = session.request

    def recorded(method, url, **kwargs):
        resp = original(method, url, **kwargs)
        body = kwargs.get("data") or kwargs.get("json")
        transcript.append(
            {
                "request": {
                    "method": method,
                    "url": str(url),
                    "headers": dict(resp.request.headers),
                    "body": body,
                },
                "response": {
                    "status_code": resp.status_code,
                    "body": resp.text,
                },
            }
        )
        return resp

    session.request = recorded
    return transcript


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    token_group = parser.add_mutually_exclusive_group(required=True)
    token_group.add_argument(
        "--request-token",
        help="single-use request_token from the browser login redirect",
    )
    token_group.add_argument(
        "--access-token", help="already-minted sandbox access_token"
    )
    parser.add_argument("--symbol", default="RELIANCE")
    parser.add_argument(
        "--output", default="/tmp/opencode/kite_sandbox_smoke_evidence.json"
    )
    args = parser.parse_args()

    from apps.execution.domain.value_objects import OrderPlacementRequest
    from apps.execution.infrastructure.brokers.zerodha_broker import ZerodhaBroker
    from apps.portfolio.domain.value_objects import Side

    broker_kwargs: dict = {"environment": "sandbox", "product": "MIS"}
    if args.request_token:
        broker_kwargs["request_token"] = args.request_token
    else:
        broker_kwargs["access_token"] = args.access_token

    # Real adapter: client=None -> built from kiteconnect + settings fallbacks.
    broker = ZerodhaBroker(**broker_kwargs)

    steps: list[dict] = []
    try:
        # Build the client WITHOUT a network call, wiretap its HTTP session,
        # then bootstrap — so the request_token exchange is on tape too.
        client = broker._build_client()
        transcript = _wiretap(client.reqsession)
        broker._client = client
        client = broker._get_client()
        steps.append({"step": "generate_session", "result": "access_token minted"})
        print(f"[ok] session established (user_id={client.profile().get('user_id')})")

        quote = client.quote([f"NSE:{args.symbol}"])[f"NSE:{args.symbol}"]
        ltp = Decimal(str(quote["last_price"]))
        resting_price = (ltp * Decimal("0.98")).quantize(
            Decimal("0.05"), rounding=ROUND_HALF_UP
        )
        steps.append(
            {
                "step": "quote",
                "symbol": f"NSE:{args.symbol}",
                "ltp": str(ltp),
                "resting_price": str(resting_price),
            }
        )
        print(f"[ok] {args.symbol} LTP={ltp} -> resting LIMIT price={resting_price}")

        request = OrderPlacementRequest(
            order_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            symbol=args.symbol,
            side=Side.LONG,
            order_type="market",  # internal type; adapter maps to LIMIT per ADR-030 §4
            quantity=Decimal(1),
            price=resting_price,
            correlation_id=uuid.uuid4(),
        )
        tag = str(request.correlation_id)

        ack1 = broker.place_order(request)
        steps.append({"step": "place_order#1", "ack": vars(ack1)})
        print(f"[ok] placed: ref={ack1.broker_order_ref}")

        ack2 = broker.place_order(request)  # identical request, same tag
        duplicate_free = (
            ack2.broker_order_ref == ack1.broker_order_ref
            and sum(1 for o in client.orders() if o.get("tag") == tag) == 1
        )
        orders_with_tag = [o for o in client.orders() if o.get("tag") == tag]
        steps.append(
            {
                "step": "place_order#2 (idempotent retry)",
                "ack": vars(ack2),
                "orders_with_tag_count": len(orders_with_tag),
                "duplicate_free": duplicate_free,
            }
        )
        print(
            f"[ok] idempotent retry reused ref={ack2.broker_order_ref} "
            f"(orders carrying tag={len(orders_with_tag)}, duplicate_free={duplicate_free})"
        )

        status_open = broker.get_order_status(ack1.broker_order_ref)
        steps.append(
            {"step": "get_order_status(after place)", "status": vars(status_open)}
        )
        print(
            f"[ok] status after place: {status_open.status} filled={status_open.filled_quantity}"
        )

        cancel = broker.cancel_order(ack1.broker_order_ref)
        steps.append({"step": "cancel_order", "result": vars(cancel)})
        print(f"[ok] cancel: cancelled={cancel.cancelled} message={cancel.message!r}")

        status_final = broker.get_order_status(ack1.broker_order_ref)
        steps.append(
            {"step": "get_order_status(after cancel)", "status": vars(status_final)}
        )
        print(f"[ok] final status: {status_final.status}")

        evidence = {
            "adapter": "ZerodhaBroker (real kiteconnect client)",
            "api_root": broker._api_root,
            "environment": broker._environment,
            "product": broker._product,
            "correlation_tag": tag,
            "steps": steps,
            "http_transcript": transcript,
        }
    except Exception as exc:  # noqa: BLE001 - smoke test reports any failure verbatim
        evidence = {
            "adapter": "ZerodhaBroker (real kiteconnect client)",
            "api_root": getattr(broker, "_api_root", "unknown"),
            "error": f"{type(exc).__name__}: {exc}",
            "completed_steps": steps,
            "http_transcript": globals().get("transcript", []),
        }
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(evidence, indent=2, default=str))
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        print(f"partial evidence written to {args.output}")
        return 1

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(evidence, indent=2, default=str))
    print(f"evidence written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
