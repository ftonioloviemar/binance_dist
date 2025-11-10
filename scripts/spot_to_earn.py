from __future__ import annotations

import logging
from typing import Dict, Sequence

from binance_client import Balance, BinanceClient, SimpleEarnProduct
from config import load_env_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("spot_to_earn")


def main() -> int:
    settings = load_env_settings(5000)
    client = BinanceClient(
        api_key=settings.api_key,
        api_secret=settings.api_secret,
        base_url=settings.base_url,
        recv_window=settings.recv_window,
    )
    try:
        balances = client.get_account_balances()
        products = client.get_simple_earn_flexible_products()
        mapping = _map_products_by_asset(products.values())
        if not mapping:
            logger.error("No Simple Earn products available for subscription")
            return 1
        transferred = 0
        for balance in _iter_target_balances(balances, mapping):
            product = mapping[balance.asset]
            amount = _clamp_subscription_amount(balance.free, product)
            if amount <= 0:
                continue
            try:
                client.subscribe_simple_earn_flexible(product_id=product.product_id, amount=amount)
            except Exception as exc:  # pragma: no cover - emergency helper
                logger.error("Failed to subscribe %s (%.8f): %s", balance.asset, amount, exc)
                continue
            logger.info("Subscribed %.8f %s into %s", amount, balance.asset, product.product_id)
            transferred += 1
        if transferred == 0:
            logger.warning("No eligible Spot balances to subscribe")
        else:
            logger.info("Completed subscriptions for %s assets", transferred)
        return 0
    finally:
        client.close()


def _iter_target_balances(balances: Sequence[Balance], mapping: Dict[str, SimpleEarnProduct]):
    for balance in balances:
        asset = balance.asset.upper()
        if asset in mapping and balance.free > 0:
            yield Balance(asset=asset, free=balance.free, locked=balance.locked)


def _map_products_by_asset(products: Sequence[SimpleEarnProduct]) -> Dict[str, SimpleEarnProduct]:
    mapping: Dict[str, SimpleEarnProduct] = {}
    for product in products:
        asset = product.asset.upper()
        status = (product.status or "").upper()
        if status not in {"SUBSCRIBABLE", "LIVE", "PURCHASING", "PURCHASABLE"}:
            continue
        if not product.can_purchase:
            continue
        mapping.setdefault(asset, product)
    return mapping


def _clamp_subscription_amount(amount: float, product: SimpleEarnProduct) -> float:
    min_amount = max(product.min_purchase_amount, 0.0)
    if amount <= 0 or amount < min_amount:
        return 0.0
    caps = [
        cap
        for cap in (
            product.max_purchase_amount,
            product.purchase_limit_per_day,
            product.purchase_limit_per_user,
            product.left_quota,
        )
        if cap and cap > 0
    ]
    if caps:
        amount = min(amount, min(caps))
    return max(amount, 0.0)


if __name__ == "__main__":
    raise SystemExit(main())
