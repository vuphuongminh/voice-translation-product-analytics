-- Activation funnel: how many users reach each step, split by acquisition channel.
--   1. signed up
--   2. completed onboarding
--   3. made a first translation
--   4. made 10+ translations (habit signal)
--   5. started a paid subscription

WITH per_user AS (
    SELECT u.user_id,
           u.channel,
           u.onboarding_completed,
           COUNT(t.translation_id)                     AS translations,
           MAX(CASE WHEN s.user_id IS NOT NULL THEN 1 ELSE 0 END) AS subscribed
    FROM users u
    LEFT JOIN translations t  ON t.user_id = u.user_id
    LEFT JOIN subscriptions s ON s.user_id = u.user_id
    GROUP BY u.user_id, u.channel, u.onboarding_completed
)
SELECT channel,
       COUNT(*)                                        AS signed_up,
       SUM(onboarding_completed)                       AS completed_onboarding,
       SUM(CASE WHEN translations >= 1  THEN 1 ELSE 0 END) AS first_translation,
       SUM(CASE WHEN translations >= 10 THEN 1 ELSE 0 END) AS ten_plus_translations,
       SUM(subscribed)                                 AS subscribed
FROM per_user
GROUP BY channel
ORDER BY signed_up DESC;
