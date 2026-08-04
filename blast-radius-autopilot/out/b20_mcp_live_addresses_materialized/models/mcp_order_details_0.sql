WITH order_details AS (
    SELECT
        -- Order information
        o.order_id,
        o.order_date,
        o.order_mode,
        o.order_status,
        o.order_total,
        o.cost_of_delivery,
        o.delivery_type,
        o.wait_till_complete_yn,
        o.payment_method_code,
        
        -- Customer information
        c.customer_id,
        c.cust_first_name,
        c.cust_last_name,
        c.cust_email,
        c.phone_number,
        c.customer_class,
        
        -- Billing address
        ba.address_line1 AS billing_address_line1,
        ba.address_line2 AS billing_address_line2,
        ba.town_city AS billing_town_city,
        bc.country_name AS billing_country,
        ba.zipcode AS billing_zipcode,
        br.region_name AS billing_region,
        
        -- Shipping address
        da.address_line1 AS shipping_address_line1,
        da.address_line2 AS shipping_address_line2,
        da.town_city AS shipping_town_city,
        dc.country_name AS shipping_country,
        da.zipcode AS shipping_zipcode,
        dr.region_name AS shipping_region,
        
        -- Warehouse information
        w.warehouse_id,
        w.warehouse_name,
        
        -- Promotion information
        p.promotion_id,
        p.promotion_name,
        p.promotion_description
        
    FROM {{ source('order_entry', 'orders') }} o
    
    -- Join to customers
    LEFT JOIN {{ source('order_entry', 'customers') }} c
        ON o.customer_id = c.customer_id
        
    -- Join to billing address through addresses table
    LEFT JOIN {{ source('order_entry', 'addresses') }} ba
        ON o.billing_address_id = ba.address_id
    LEFT JOIN {{ source('order_entry', 'countries') }} bc
        ON ba.country_id = bc.country_id
    LEFT JOIN {{ source('order_entry', 'regions') }} br
        ON ba.region_id = br.region_id
        
    -- Join to shipping address through addresses table
    LEFT JOIN {{ source('order_entry', 'addresses') }} da
        ON o.delivery_address_id = da.address_id
    LEFT JOIN {{ source('order_entry', 'countries') }} dc
        ON da.country_id = dc.country_id
    LEFT JOIN {{ source('order_entry', 'regions') }} dr
        ON da.region_id = dr.region_id
        
    -- Join to warehouse
    LEFT JOIN {{ source('order_entry', 'warehouses') }} w
        ON o.warehouse_id = w.warehouse_id
        
    -- Join to promotions
    LEFT JOIN {{ source('order_entry', 'promotions') }} p
        ON o.promotion_id = p.promotion_id
),

order_line_items AS (
    SELECT
        oi.order_id,
        oi.line_item_id,
        oi.unit_price,
        oi.quantity,
        oi.unit_price * oi.quantity AS line_total,
        oi.dispatch_date,
        oi.return_date,
        oi.gift_wrap,
        oi.condition,
        oi.estimated_delivery,
        
        -- Product information
        p.product_id,
        p.product_name,
        p.product_description,
        p.list_price,
        p.product_status,
        
        -- Category information
        pc.category_id,
        pc.category_name,
        
        -- Inventory information
        i.quantity_on_hand,
        CASE
            WHEN i.quantity_on_hand <= i.restock_level THEN 'Low Stock'
            WHEN i.quantity_on_hand > i.restock_level AND i.quantity_on_hand < i.max_stock_level THEN 'In Stock'
            WHEN i.quantity_on_hand >= i.max_stock_level THEN 'Overstocked'
            ELSE 'Unknown'
        END AS stock_status
        
    FROM {{ source('order_entry', 'order_items') }} oi
    
    -- Join to products
    LEFT JOIN {{ source('order_entry', 'products') }} p
        ON oi.product_id = p.product_id
        
    -- Join to product categories
    LEFT JOIN {{ source('order_entry', 'product_categories') }} pc
        ON p.category_id = pc.category_id
        
    -- Join to inventory for the corresponding warehouse of the order
    LEFT JOIN {{ source('order_entry', 'orders') }} o
        ON oi.order_id = o.order_id
    LEFT JOIN {{ source('order_entry', 'inventories') }} i
        ON p.product_id = i.product_id AND o.warehouse_id = i.warehouse_id
)

SELECT
    -- Order header information
    od.*,
    
    -- Order line item information
    li.line_item_id,
    li.product_id,
    li.product_name,
    li.product_description,
    li.category_id,
    li.category_name,
    li.unit_price,
    li.quantity,
    li.line_total,
    li.dispatch_date,
    li.return_date,
    li.gift_wrap,
    li.condition,
    li.estimated_delivery,
    li.list_price,
    li.product_status,
    li.quantity_on_hand,
    li.stock_status,
    
    -- Calculate discount amount and percentage
    CASE 
        WHEN li.list_price > 0 THEN (li.list_price - li.unit_price) 
        ELSE 0 
    END AS discount_amount,
    
    CASE 
        WHEN li.list_price > 0 THEN ((li.list_price - li.unit_price) / li.list_price) * 100 
        ELSE 0 
    END AS discount_percent,
    
    -- Delivery status calculation
    CASE
        WHEN li.dispatch_date I... [truncated]
