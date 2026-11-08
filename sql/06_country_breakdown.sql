-- Activation and paid conversion by country.
-- Helps decide which markets to localise, market or price for first.

WITH per_user AS (
    SELECT u.user_id,
           u.country,
           COUNT(t.translation_id)                               AS translations,
           MAX(CASE WHEN s.user_id IS NOT NULL THEN 1 ELSE 0 END) AS subscribed
    FROM users u
    LEFT JOIN translations t  ON t.user_id = u.user_id
    LEFT JOIN subscriptions s ON s.user_id = u.user_id
    GROUP BY u.user_id, u.country
)
SELECT country,
       COUNT(*)                                                       AS users,
       ROUND(AVG(CASE WHEN translations >= 1 THEN 1.0 ELSE 0 END), 4) AS activation_rate,
       ROUND(AVG(CASE WHEN translations >= 10 THEN 1.0 ELSE 0 END), 4) AS habit_rate,
       ROUND(AVG(subscribed * 1.0), 4)                                AS paid_conversion,
       ROUND(1.0 * SUM(translations)
             / NULLIF(SUM(CASE WHEN translations >= 1 THEN 1 ELSE 0 END), 0), 1)
                                                                      AS translations_per_active_user
FROM per_user
GROUP BY country
ORDER BY users DESC;
