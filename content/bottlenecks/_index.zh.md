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
- front matter：`title` 是瓶颈名；`num` 是卡片编号，显示成 B<num>，按收录先后发，发出后不改、不复用，新卡片取下一个号；卡片按编号排，所以新卡片排在最后，不另设排序字段；`signal` 是查找表里的一行；`source` 是它在 intel/intel-performance-skills（3e33aec）里对应的文件。
- 正文是一整块 `>` 引用，分点写信号、原因、修法、其他要点、验证、原理。
- 加一种瓶颈，只要在这里新增这两个文件。速查页的查找表、卡片、编号和锚点自动带上；讲到它原理的文章，在“应用”一节追加一行 `bottleneck`。
- 卡片出现的地方都带编号，写成“B6 伪共享”，编号由短代码从 `num` 读出来拼上，不手写：文章末尾嵌入用 `bottleneck`，正文里点名一张卡片用 `bottleneck-ref`（默认是链接；第二个参数 `plain` 只出文字，`num` 只出编号）。
