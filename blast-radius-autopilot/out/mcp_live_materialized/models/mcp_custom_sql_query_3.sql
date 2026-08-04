SELECT 
    promotion_name,
    COUNT(DISTINCT order_id) as orders_with_promotion,
    SUM(order_total) as total_revenue,
    AVG(order_total) as average_order_value,
    AVG(discount_percent) as average_discount_percent
FROM order_entry_db.analytics.order_details
WHERE promotion_name IS NOT NULL
GROUP BY promotion_name
ORDER BY total_revenue DESC
