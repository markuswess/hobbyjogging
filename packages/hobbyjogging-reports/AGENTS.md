# Package instructions: hobbyjogging-reports

Analysis, Markdown reports, charts and the dashboard. The shared rules are in
the repo's `docs/AGENTS.md`; this file only adds package workflow.

## Dashboard changes

- After any dashboard or chart change, regenerate the dashboard and look at
  the affected page before calling it done. Passing tests do not catch a
  broken layout, a mis-scaled axis or a missing series.
- Build into a scratch directory, e.g.
  `./dashboard.sh --no-open --output /tmp/opencode/site-<name>`, never over
  an existing site. Use the real database for the real shape and the demo
  story for synthetic cases.
