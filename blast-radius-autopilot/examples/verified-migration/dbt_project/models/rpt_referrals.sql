-- rpt_referrals: one row per signup with its referral code, for the growth funnel.
-- Owned by team:growth-eng. Downstream of analytics.fct_signups.
SELECT
    s.signup_id,
    s.account_id,
    s.referrer_code,
    s.signed_up_at
FROM analytics.fct_signups s
