-- Top language pairs by volume, with the share of all translations.

SELECT source_lang || ' -> ' || target_lang                AS language_pair,
       COUNT(*)                                              AS translations,
       COUNT(DISTINCT user_id)                               AS users,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM translations), 2) AS share_pct
FROM translations
GROUP BY source_lang, target_lang
ORDER BY translations DESC
LIMIT 15;
