-- rpt_orders_by_region: completed orders with the ship-to ZIP, for regional reporting.
-- Owned by team:analytics-eng. Downstream of analytics.fct_orders.
SELECT
    o.order_id,
    o.customer_zip,
    o.amount
FROM analytics.fct_orders o
WHERE o.status = 'complete'
