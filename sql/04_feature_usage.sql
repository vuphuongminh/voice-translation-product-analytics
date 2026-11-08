-- Weekly usage of the two translation modes and their quality signals.

SELECT DATE(requested_at, '-' || ((CAST(STRFTIME('%w', requested_at) AS INTEGER) + 6) % 7) || ' days')
           AS week_start,
       mode,
       COUNT(*)                          AS translations,
       COUNT(DISTINCT user_id)           AS users,
       ROUND(AVG(latency_ms), 0)         AS avg_latency_ms,
       ROUND(AVG(success), 4)            AS success_rate
FROM translations
GROUP BY week_start, mode
ORDER BY week_start, mode;
