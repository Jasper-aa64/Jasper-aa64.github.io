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
- Front matter: `title` (the bottleneck's name), `num` (the card's number, shown as B<num>: given in the order cards are added, never changed or reused, a new card takes the next one; cards are shown in number order, so new cards go last and there is no separate order field), `signal` (one line for the lookup table), `source` (the matching file in intel/intel-performance-skills at 3e33aec).
- Body: one `>` quote with the points Signal / Cause / Fix / other points / Verify / Mechanism.
- Adding a bottleneck means adding its two files here. The reference page lists, numbers, tabulates and anchors it automatically; a post that explains its mechanism gets one more `bottleneck` line in its In Practice section.
- Wherever a card appears it carries its number, as in "B6 False Sharing", read from `num` by a shortcode rather than typed: `bottleneck` embeds a card at the end of a post, `bottleneck-ref` names one in running text (a link by default; a second argument `plain` gives the words only, `num` the number only). A card body cannot use shortcodes (it goes out as written): to link another card from inside a card, write the full path with that card's title as the link text, as in `[Serial Accumulator](/ref/bottlenecks/#serial-accumulator)`, and the `bottleneck-body` partial shows it as "B1 Serial Accumulator".
