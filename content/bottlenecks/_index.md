---
title: "Bottleneck cards (source files)"
build:
  render: never
  list: never
cascade:
  build:
    render: never
    list: local
---

Source files of the bottleneck cards; nothing in this folder gets its own URL.

- Each card is `<id>.md` (English) and `<id>.zh.md` (Chinese). The file name is the card's id: its anchor on /ref/bottlenecks/ and the argument of the `bottleneck` shortcode that embeds it at the end of a post.
- Front matter: `title` (the bottleneck's name), `weight` (display order; a new card takes the next number, so new cards go last), `signal` (one line for the lookup table), `source` (the matching file in intel/intel-performance-skills at 3e33aec).
- Body: one `>` quote with the points Signal / Cause / Fix / other points / Verify / Mechanism.
- Adding a bottleneck means adding its two files here. The reference page lists, tabulates and anchors it automatically; a post that explains its mechanism gets one more `bottleneck` line in its In Practice section.
