# Shadow State Database Isolation

Public market observations, indicators, and aggregate scenario results belong in `state/market_insights.db`. Because a longitudinal shadow session must retain virtual quantities initially derived from actual Spot and Simple Earn holdings, persist only the minimum per-policy inventory and continuation state in the separate local `state/shadow_portfolios.db`. Keep raw source snapshots and credentials out of both shadow state and market-insights persistence; do not place synthetic results in `state/performance.db`.
