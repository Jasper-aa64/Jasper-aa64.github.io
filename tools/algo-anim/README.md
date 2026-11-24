# algo 动画和配图

`ui.py` 是分步动画的统一规范：图标按钮（重来 / 上一步 / 播放暂停 / 下一步）、步数和进度条、图例色块、带步号的说明面板，按最高的一步锁定高度，翻页时窗口不跳。新动画都用它。

在仓库根目录运行：

```
python tools/algo-anim/gen_insert.py static/maps tools/algo-anim/insert_tpl.html   # L3 线性基插入
python tools/algo-anim/gen_gauss.py . tools/algo-anim                              # L2 高斯消元分步 + 开关灯矩阵图
python tools/algo-anim/gen_svg.py static/images/algo                               # L3 规范化/第 k 小、区间线性基两张图
```
