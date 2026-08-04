-- rpt_loyalty: customer loyalty tier by region.
-- Owned by team:retail-data. Downstream of retail.customers.
SELECT
    customer_id,
    loyalty_tier,
    region
FROM retail.customers
