SELECT 
    order_date,
    category_name,
    COUNT(DISTINCT order_id) as order_count,
    SUM(line_total) as total_sales
FROM order_entry_db.analytics.order_details
WHERE category_name IS NOT NULL
GROUP BY order_date, category_name
ORDER BY order_date DESC, total_sales DESC
