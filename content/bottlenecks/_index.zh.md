---
title: "瓶颈卡片（源文件）"
build:
  render: never
  list: never
cascade:
  build:
    render: never
    list: local
---

瓶颈卡片的源文件，这个目录里的文件都不单独生成网页。

- 每张卡片是 `<id>.zh.md`（中文）和 `<id>.md`（英文）两个文件。文件名就是卡片的 id：它在 /zh/ref/bottlenecks/ 上的锚点，也是文章末尾嵌入卡片时短代码 `bottleneck` 的参数。
- front matter：`title` 是瓶颈名；`weight` 是显示顺序，新卡片取下一个数，所以排在最后；`signal` 是查找表里的一行；`source` 是它在 intel/intel-performance-skills（3e33aec）里对应的文件。
- 正文是一整块 `>` 引用，分点写信号、原因、修法、其他要点、验证、原理。
- 加一种瓶颈，只要在这里新增这两个文件。速查页的查找表、卡片和锚点自动带上；讲到它原理的文章，在“实际优化里怎么用”一节追加一行 `bottleneck`。
