-- rpt_signups_by_plan: signups per plan, with the referral code carried through.
-- Owned by team:growth-eng. Downstream of analytics.fct_signups.
SELECT
    s.signup_id,
    s.plan,
    s.referrer_code
FROM analytics.fct_signups s
WHERE s.plan IS NOT NULL
