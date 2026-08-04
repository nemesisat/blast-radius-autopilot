SELECT 
    order_mode,
    COUNT(DISTINCT order_id) as order_count,
    SUM(order_total) as total_revenue,
    AVG(order_total) as average_order_value
FROM order_entry_db.analytics.order_details
GROUP BY order_mode
ORDER BY total_revenue DESC
