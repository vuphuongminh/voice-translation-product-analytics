-- Daily active users (DAU), weekly active users (WAU) and stickiness (DAU / MAU).
-- A user is "active" on a day if they started at least one session that day.

WITH daily AS (
    SELECT DATE(session_start) AS activity_date,
           user_id
    FROM sessions
    GROUP BY 1, 2
),
dates AS (
    SELECT DISTINCT activity_date FROM daily
)
SELECT d.activity_date,
       (SELECT COUNT(*) FROM daily x
         WHERE x.activity_date = d.activity_date)                          AS dau,
       (SELECT COUNT(DISTINCT user_id) FROM daily x
         WHERE x.activity_date BETWEEN DATE(d.activity_date, '-6 days')
                                   AND d.activity_date)                   AS wau,
       (SELECT COUNT(DISTINCT user_id) FROM daily x
         WHERE x.activity_date BETWEEN DATE(d.activity_date, '-29 days')
                                   AND d.activity_date)                   AS mau
FROM dates d
ORDER BY d.activity_date;
