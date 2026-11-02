---
title: "Trading System Notes #21: A-Share Level-2 Market Data"
date: 2026-11-03T00:00:00+08:00
slug: "a-share-level2-market-data"
description: "A factor computed by research on historical Level-2 data often fails to match once it is moved to live tick-by-tick computation, and the cause is usually not the formula but the data: a cumulative field that was never differenced, cancels that live in another feed, and an ordering between two records that only the sequence number can settle. Part 1 covers what snapshots, order-by-order and trade-by-trade data each record, how Shanghai and Shenzhen differ, and how to use sequence numbers."
summary: "What snapshots, order-by-order and trade-by-trade data each record, how Shanghai and Shenzhen differ, and how to use sequence numbers."
chapter: 4
categories: [Systems]
tags: [level2, market-data, a-share, tick-data, order-book, quant]
toc: true
---

A researcher computes a factor in Python on historical Level-2 data; it has to move into a live C++ system that computes it tick by tick, and the two results have to match value for value. When they don't, the cause is often not the formula but the data itself: whether a field is cumulative or incremental, which feed a cancel is recorded in, and which of two records with the same timestamp came first. So before writing a factor, you need to know what each kind of data actually records. Part 1 covers what snapshots, order-by-order data and trade-by-trade data each record, how the Shanghai and Shenzhen exchanges record them differently, and how to use sequence numbers. Part 2 covers linking trades to orders, determining the aggressor side, and what the data looks like during call auctions. The order-book post after that rebuilds the book from tick data and checks it against snapshots.

## 1. Three Kinds of Data: What Each One Records

### 1.1 Level-1 and Level-2: the Same Market at Different Resolutions

While the exchange matches orders, the order book changes all the time: orders are placed, orders are cancelled, orders trade. Level-1 data only gives the state at fixed intervals: roughly one snapshot every 3 seconds, with five levels of bid/ask prices and sizes, the last price, and cumulative volume and turnover. Level-2 adds three things: snapshots go to ten levels and carry the sizes of the first 50 resting orders at the best bid and the best ask (the order queue); order-by-order data, one message per order placed or cancelled; and trade-by-trade data, one message per match.

The difference is not just the number of levels. **A snapshot is the result; tick data is the process**: a snapshot tells you what the book looks like 3 seconds later, tick data tells you what happened in those 3 seconds and in what order. A factor built only on snapshots has lost all ordering within the 3 seconds; to know who traded aggressively, or when a large order was placed and then pulled, you need tick data. The volumes differ a lot too: about 5000 stocks, each with at most about 4800 snapshots a day, is a little over twenty million rows; tick data is several hundred million rows a day.

### 1.2 Snapshots: One Every 3 Seconds, and Cumulative Fields Must Be Differenced

The main fields of a Level-2 snapshot:

| Group | Fields |
|---|---|
| Time and status | snapshot time, trading phase (opening call auction, continuous trading, break, closing call auction, halted, …) |
| Prices | previous close, open, high, low, last; upper and lower price limits |
| Book | ten bid prices and sizes, ten ask prices and sizes |
| Cumulative trading | number of trades, total volume, total turnover |
| Resting-order totals | total bid size, total ask size, weighted average bid and ask prices |

Number of trades, volume and turnover are all cumulative from the open. To get the volume over an interval, subtract the cumulative volume of one snapshot from the next. On the research side that is typically `df['volume'].diff()`; in C++, computing row by row, it means remembering the previous cumulative value and subtracting. The first snapshot of the day is where the two sides diverge: pandas' `diff()` gives NaN, while in C++, if the previous value starts at 0, you get all the volume since the open. **When differencing cumulative values, how to treat the first snapshot has to be agreed in advance**, or the first row of every day will mismatch.

3 seconds is an upper bound on the cadence, not a guarantee. For a stock whose book and trades haven't changed, there is usually no new snapshot in those 3 seconds, and a quiet stock getting only a few snapshots a minute is common. So when cutting 3-second or 1-minute bars, some buckets contain no snapshot: whether to carry the previous one forward or leave it empty is another thing to align with research.

A snapshot's timestamp is the moment the exchange generated it, which is not on the same clock tick as tick data, nor at the same time precision. Trades within the same millisecond can fall on either side of a snapshot, so "add up all trades timestamped before this snapshot" does not necessarily equal its cumulative volume. Aligning snapshots and tick data exactly means rebuilding state from tick data and comparing; the order-book post goes into it.

Prices are integers in the data, scaled by an agreed factor (commonly 10000); take the factor from the data vendor's documentation and check it against real data. Turnover has a trap as well: some vendors give trade turnover as whole yuan with the fractional part dropped. You don't notice while volumes are multiples of 100 shares, but for a 201-share trade on the STAR Market, or a sale of an odd lot, the turnover comes out a few tenths of a yuan short. To be exact to the fen, compute price × quantity yourself.

### 1.3 Order-by-Order and Trade-by-Trade Data: the Two Exchanges Record Them Differently

Both Shanghai and Shenzhen publish an order feed and a trade feed, but what goes into each feed differs:

| | Shenzhen | Shanghai |
|---|---|---|
| What the order feed records | every new order the exchange receives, with the original order quantity | the part that enters the book: orders filled entirely on arrival are not published, partially filled ones only with the remaining quantity |
| Order feed record types | limit, market, best-of-own-side | add (A), delete (D), plus product status (S) |
| Where cancels go | in the trade feed: execution type "cancel", price 0, only one of the buy/sell order sequence numbers non-zero | in the order feed: type delete |
| Aggressor side of a trade | no flag in the trade record; you determine it yourself (Part 2) | the trade record carries a flag: B aggressive buy, S aggressive sell, N unknown |
| Sequence number | per-channel message record number, shared by orders and trades | per-channel business index, shared by orders and trades |

Two things in the table are the easiest to get wrong.

The first is the quantity in Shanghai's order feed. A 500,000-share buy order arrives and immediately takes 400,000 shares from the first three ask levels; the remaining 100,000 rest on the bid, and Shanghai's order feed shows an add of 100,000 shares. A large order that fills completely on arrival never appears in the order feed at all; it only leaves a few trades with the same buy order number in the trade feed. Shenzhen publishes a 500,000-share order in both cases. **Shenzhen's order feed records what was submitted; Shanghai's records what ended up resting on the book.** The same "large-order share" factor has to be written separately for the two exchanges, or in Shanghai the immediately filled part has to be added back from the trade feed by order number.

The second is where cancels live. To compute cancelled volume, in Shenzhen you pick the "cancel" records out of the trade feed, in Shanghai the deletes out of the order feed; subscribe to only one feed and you miss half the events. Shenzhen's cancel records have price 0, so computing an average price straight from the trade feed lets these rows skew the result; to know at which price the cancelled order was resting, you look up the original order by its sequence number (Part 2).

Put the two tables together: Shanghai's order feed records what was placed on and removed from the book, and its trade feed records matches; Shenzhen's order feed records what the exchange received, and its trade feed records how orders left the book, by trading or by being cancelled. The split differs between the two exchanges, so a factor cannot use the same extraction logic for both.

### 1.4 Sequence Numbers: Order Within a Channel, and Gaps Mean Lost Messages

The exchange assigns stocks to a number of channels, and within each channel tick records carry a sequence number that starts at 1 and increases without gaps. On both exchanges orders and trades share one numbering, so within a channel the order and trade feeds can be merged by sequence number into one stream that restores the order in which the exchange processed them.

Timestamps won't do for this, because they only go to the millisecond and one millisecond can hold many records; an order and the trades it triggers often have the same time. Sort the order feed and the trade feed by time separately and then interleave them, and the order among records with equal times is lost; when rebuilding the book, getting that order wrong produces things like "a trade against an order that hasn't been placed yet". **Within a channel, order is defined by the sequence number alone.** Sequence numbers in different channels each start at 1 and cannot be compared; between two stocks in different channels you can only align roughly by time.

Because the numbers have no gaps, they also detect lost messages: receiving 1001, 1002, 1004 means 1003 is missing. A live system has to detect the gap and fill it (a retransmission from the vendor, or a backfill); in backtest data a gap should be flagged. The missing record may be exactly a cancel, after which the rebuilt book never matches the exchange's again. Conversely, after a reconnect the vendor may resend a stretch, and deduplicating by sequence number handles it.

One more pair of fields has similar names and is easy to confuse. Shanghai's business index numbers messages, while the buy and sell order numbers in a Shanghai trade refer to the order's original order number, not its business index; in Shenzhen, the buy and sell order sequence numbers in a trade are exactly the message record numbers of those order records. Use the wrong field when looking up orders from trades and not a single one matches. How the lookup works and what it lets you compute is the subject of Part 2.
