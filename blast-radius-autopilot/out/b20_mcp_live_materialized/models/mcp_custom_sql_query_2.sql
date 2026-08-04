SELECT 
    category_name,
    COUNT(DISTINCT order_id) as orders_count,
    SUM(line_total) as total_revenue,
    AVG(line_total) as average_order_value
FROM order_entry_db.analytics.order_details
WHERE category_name IS NOT NULL
GROUP BY category_name
ORDER BY total_revenue DESC
