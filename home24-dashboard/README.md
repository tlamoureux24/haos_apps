# HOME24 dashboard

Prototype source for the `TDB` Home Assistant dashboard.

## Files

- `home24-card.js`: responsive Home Assistant custom card.
- `tdb-dashboard.yaml`: Lovelace dashboard configuration.
- `preview.html`: standalone responsive preview with mocked entity states.

## Design contract

- One immersive home screen, adapted to HOME24.
- Dynamic scene selected from sun state, local time and weather condition.
- The configured outdoor camera is used first, so the scene naturally follows the
  real weather and daylight at HOME24; local images remain available as fallback.
- Desktop: navigation, live energy scene and battery/production summary.
- Mobile: single readable flow with compact horizontal navigation.
- All values come from Home Assistant entities; no hard-coded production values.
- Secondary views are explicit placeholders until their content is designed.

## Background assets expected in Home Assistant

The card expects these files under `/config/www/home24/`:

- `home24-day.webp`
- `home24-cloudy.webp`
- `home24-rain.webp`
- `home24-sunset.webp`
- `home24-night.webp`

They are referenced in Lovelace as `/local/home24/<filename>`.
