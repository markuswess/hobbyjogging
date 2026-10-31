# hobbyjogging-import

Import and normalize training data from external sources.

Planned importers:

- Garmin `.fit` files
- Intervals.icu
- Runalyze
- historical spreadsheet exports

The importers write to the canonical database; reports read from it through
`hobbyjogging-reports`.
