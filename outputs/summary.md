# Analysis summary (generated)

All figures come from the synthetic dataset in this repository.

## Engagement
- Peak DAU: 265 on 2026-04-25
- Stickiness on the last day (DAU/MAU): 8.3%

## Activation funnel
- signed_up: 5,000 users (100.0% of signups, 100.0% of previous step)
- completed_onboarding: 3,884 users (77.7% of signups, 77.7% of previous step)
- first_translation: 3,420 users (68.4% of signups, 88.0% of previous step)
- ten_plus_translations: 2,140 users (42.8% of signups, 62.6% of previous step)
- subscribed: 181 users (3.6% of signups, 8.5% of previous step)

## Engine v2 latency impact (median, 95% bootstrap CI)
- voice_to_text: 899 ms -> 631 ms (-29.8%, CI -31.0% to -28.6%); success rate 93.3% -> 95.9%
- voice_to_voice: 1406 ms -> 981 ms (-30.2%, CI -31.4% to -29.1%); success rate 92.7% -> 96.2%

## Week-1 retention, cohorts before vs after engine v2 (observational)
- engine-v1: 36.3% (1,974 users in 9 cohorts)
- engine-v2: 39.7% (2,009 users in 6 cohorts)
