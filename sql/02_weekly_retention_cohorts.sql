-- Weekly retention by signup cohort.
-- cohort_week   : Monday of the week the user signed up
-- week_number   : weeks since signup (0 = signup week)
-- retained_users: users from the cohort with at least one session in that week

WITH cohort AS (
    SELECT user_id,
           signup_date,
           DATE(signup_date, '-' || ((CAST(STRFTIME('%w', signup_date) AS INTEGER) + 6) % 7) || ' days')
               AS cohort_week
    FROM users
),
activity AS (
    SELECT DISTINCT s.user_id,
           CAST((JULIANDAY(DATE(s.session_start)) - JULIANDAY(c.signup_date)) / 7 AS INTEGER)
               AS week_number
    FROM sessions s
    JOIN cohort c ON c.user_id = s.user_id
),
cohort_size AS (
    SELECT cohort_week, COUNT(*) AS cohort_users
    FROM cohort
    GROUP BY cohort_week
)
SELECT c.cohort_week,
       cs.cohort_users,
       a.week_number,
       COUNT(DISTINCT a.user_id)                                AS retained_users,
       ROUND(1.0 * COUNT(DISTINCT a.user_id) / cs.cohort_users, 4) AS retention_rate
FROM activity a
JOIN cohort c       ON c.user_id = a.user_id
JOIN cohort_size cs ON cs.cohort_week = c.cohort_week
WHERE a.week_number BETWEEN 0 AND 8
GROUP BY c.cohort_week, cs.cohort_users, a.week_number
ORDER BY c.cohort_week, a.week_number;
