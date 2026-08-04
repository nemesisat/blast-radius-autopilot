{{
    config(
        materialized='incremental',
        post_hook=[
            "DELETE FROM {{ this }} WHERE as_of_date < dateadd(day, -5, current_timestamp())"
        ]
    )
}}

select
  order_id
  , customer_id
  , order_status
  , order_total
  , updated_at::date as as_of_date

from
  {{ ref('order_details') }}

{% if is_incremental() %}

  -- this filter will only be applied on an incremental run
  where updated_at > (select max(as_of_date) from {{ this }})

{% endif %}
