---
title: "P1: Probability and Expectation"
date: 2026-11-26
slug: "p1-probability-expectation"
description: "Expectation is a probability-weighted average and it is linear: the expected count of something splits into indicator variables (CF 1612E, 2026 Jilin Provincial M counting colour runs); the expected maximum comes from the distribution function (CF 453A); expected time until stopping runs backwards from the end (ABC 184D, the self-loop in CF 908D, ABC 144F where removing one edge changes one node); with cycles, write the equations and eliminate by hand when the structure allows (CF 1453D) or with Gaussian elimination; when everything changes at once, find a potential that rises by exactly 1 per round in expectation (2025 CCPC Harbin H). It ends with techniques for deriving the formulas: tracking several moments together (Luogu P1654 OSU!), phases, the tail sum, and the traps with products and ratios. With 9 practice problems."
weight: 18
math: true
toc: true
---
> The essence of expectation: a probability-weighted average that is linear, so the expectation of a total is the sum of the expectations of its parts.

Shuffle a list of numbers that may repeat (say `1 1 2 2`) and merge adjacent equal numbers into runs: on average, how many runs are there?

- **The distribution is out of reach**: the number of orders with "exactly $j$ runs" has no usable formula.
- **Split it and it becomes easy**: runs = 1 + the number of adjacent pairs that are not equal. Each "this pair differs" is 0 or 1, so its average is its probability; the shuffle treats every position alike, so each pair differs with the probability that two numbers drawn at random differ. For `1 1 2 2` that probability is $\frac23$, and the average is $1 + 3 \times \frac23 = 3$ runs.
- **That step is linearity of expectation**: the expectation of a sum is the sum of the expectations, with no independence needed; adjacent pairs share a number and still split. The first move on any expectation problem is to look for such a split; if it does not split, define states and write equations; if the states form cycles, solve a system. The full solution of this problem is in 3.2.

This post first says what expectation is and why it splits (section 1), then sorts the problems it solves (section 2), then goes method by method: indicator variables (section 3), the distribution function (section 4), expectation DP backwards from the end (section 5), equations when there are cycles (section 6), and a potential when everything changes together (section 7), and finally collects the techniques for deriving the formulas (section 8). Each section ends with examples. How to solve the cyclic systems is in [L2 Gaussian Elimination](/algo/l2-gaussian-elimination/).

<style>.chroma .line.hl{background:rgba(56,139,253,.15)}</style>

## 1. What Expectation Is and Why It Splits

### 1.1 Expectation: A Probability-Weighted Average

**The expectation of a random variable $X$ multiplies each value by the probability of getting it and adds up.**

1. **A random variable is a number attached to the outcome of a random experiment**
   - **It maps each outcome to a number**: for two dice rolls, "the sum", "the maximum" and "whether a 6 appeared" are all random variables.
   - **At heart it is a function**: it takes one outcome of the experiment and returns a number. What is random is which outcome occurs; the rule itself is fixed.
   - **Turning outcomes into numbers is what lets us average and add**: a raw outcome such as "the shuffle comes out as `1212`" cannot be added; once mapped to numbers, we can take expectations and split them into sums.
   - **Its distribution is the probability of each value**: $P(X = x)$. Capital $X$ is the rule; lowercase $x$ is one particular value it takes.
2. **Expectation is a weighted average**
   - **Definition**: $E[X] = \sum_x x \cdot P(X = x)$.
   - **Meaning**: repeat the experiment independently many times and the average of $X$ approaches $E[X]$.
   - **Example**: one die has $E[X] = \frac{1 + 2 + \cdots + 6}{6} = 3.5$.
3. **One experiment carries many random variables, each with its own values**
   - **Example: shuffle `1 1 2 2`**: the run count $R$ takes 2, 3 or 4; whether numbers $k$ and $k + 1$ differ, written $I_k$, takes only 0 or 1 (an indicator, 1.3).
   - **They are different translations of the same outcome**: for `1212`, $R = 4$ and $I_1 = I_2 = I_3 = 1$; for `1122`, $R = 2$ and $I_1 = 0, I_2 = 1, I_3 = 0$.
   - **In every outcome, $R = 1 + I_1 + I_2 + I_3$**: the problem asks about $R$, whose distribution is hard; split into the $I_k$, each needs only one probability.

### 1.2 Linearity: The Expectation of a Sum Is the Sum of Expectations

**$E[X + Y] = E[X] + E[Y]$ holds for any two random variables, independent or not.**

1. **List every possible outcome in one ledger**
   - **Each row is one outcome, with its probability**: the row records this outcome's $X$, $Y$ and $X + Y$.
   - **An expectation is the probability-weighted average of one column**: $E[X]$ averages the $X$ column, $E[X + Y]$ averages the $X + Y$ column.
   - **In every row, the $X + Y$ entry is the $X$ entry plus the $Y$ entry**: with the same weights, adding then averaging equals averaging then adding, so $E[X + Y] = E[X] + E[Y]$.
2. **Example: two coins, three kinds of dependence**
   - **Notation**: $X$ is whether the first coin is heads (heads = 1), $Y$ the same for the second coin.
   - **Independent coins**: 4 rows, $(0, 0), (0, 1), (1, 0), (1, 1)$, each $\frac{1}{4}$; $X + Y$ is $0, 1, 1, 2$, expectation $\frac{0 + 1 + 1 + 2}{4} = 1$.
   - **The second coin copies the first**: only 2 rows, $(0, 0), (1, 1)$, each $\frac{1}{2}$; $X + Y$ is $0, 2$, expectation $\frac{0 + 2}{2} = 1$.
   - **The second coin is the opposite of the first**: 2 rows, $(0, 1), (1, 0)$, each $\frac{1}{2}$; $X + Y$ is always 1, expectation 1.
   - **Conclusion**: the distribution of $X + Y$ is completely different in the three cases ($0/1/2$ with $\frac{1}{4}/\frac{1}{2}/\frac{1}{4}$, $0/2$ half each, always 1), but each coin on its own is heads half the time, $E[X] = E[Y] = \frac{1}{2}$, so $E[X + Y]$ is 1 every time.
3. **Dependence only decides how the parts pair up; the total's average sees only each part's own average**
   - **Being tied together means not independent**: $X$ and $Y$ are independent when knowing $X$ does not change the probabilities of $Y$'s values; as a formula, $P(X = x, Y = y) = P(X = x) \cdot P(Y = y)$ for all $x, y$.
   - **Examples**:
     - **The copying coin**: $P(Y = 1) = \frac12$ on its own; once $X = 1$ is known, $Y$ is certainly 1, so they are not independent.
     - **Shuffling `1 1 2 2` is drawing two 1s and two 2s from a bag one by one**: $I_2$ asks whether the third draw differs from the second, which depends on what is left in the bag at the third draw.
       - **$I_2$ on its own**: after the second draw, 3 cards remain and 2 of them differ from it, so $P(I_2 = 1) = \frac23$.
       - **Given $I_1 = 1$**: the first two are one 1 and one 2, the bag holds one 1 and one 2, and the third draw differs from the second only half the time: $\frac12$.
       - **Given $I_1 = 0$**: the first two are equal, say two 1s, the bag holds only 2s, and the third draw always differs from the second: probability 1.
       - **$I_2$'s probability changes with $I_1$, so they are not independent**: both pairs share the second draw, and what the first two draws take decides what is left.
   - **Dependence changes which pairings appear in the ledger**: with copying, $(0, 1)$ never appears; with the opposite coin, $(0, 0)$ never appears; the row probabilities change too.
   - **Each column's average looks only at that column**: $E[X]$ uses only the $X$ values and the row probabilities, not how $Y$ pairs with them. So as long as each part's own average stays the same, the total's average is the same however the parts are tied together.
   - **If the dependence changes a part's own average, use the new average**: linearity says "the total's average is the sum of the parts' averages", not "the parts' averages never change". For example, if the second coin is heads whenever the first is heads and is tossed independently otherwise, $E[Y] = \frac{1}{2} + \frac{1}{2} \cdot \frac{1}{2} = \frac{3}{4}$, and $E[X + Y] = \frac{1}{2} + \frac{3}{4} = \frac{5}{4}$.
   - **In a problem, compute each part on its own, ignoring how it is tied to the others**: when a list of numbers is shuffled, adjacent pairs 1 and 2 share a number, so "pair 1 differs" and "pair 2 differs" are tied together; still, compute each pair's probability of differing alone and add them to get the expected number of differing pairs (3.2).
   - **When the quantity is about several parts at once, the dependence cannot be avoided**: products, joint occurrence and maxima all depend on the pairing; see the next point and 8.5.
4. **Why products do not split**
   - **Compute $XY$ for the same coins**: independent, only the $(1, 1)$ row is 1, expectation $\frac{1}{4}$; copying, $(1, 1)$ is half the ledger, expectation $\frac{1}{2}$; opposite, there is no $(1, 1)$ row, expectation 0.
   - **Reason**: $E[XY]$ depends on whether $Y$ is also 1 in the rows where $X = 1$, which is exactly the dependence. Only for independent coins does it equal $E[X] \cdot E[Y] = \frac{1}{4}$.
5. **As a formula: "average over the ledger" written as sums**
   - **Notation**: $P(X = x, Y = y)$ is the joint distribution, the probability of row $(x, y)$ in the ledger above.
   - **Step 1, average over rows**: multiply each row's $x + y$ by the row's probability and add.
     $$E[X + Y] = \sum_{x, y} (x + y) \cdot P(X = x, Y = y).$$
   - **Step 2, split each row in two**: split the $X + Y$ column into the $X$ column and the $Y$ column and sum them separately.
     $$= \sum_{x, y} x \cdot P(X = x, Y = y) + \sum_{x, y} y \cdot P(X = x, Y = y).$$
   - **Step 3, group the rows by $x$**: in the first sum, the rows with the same $x$ have probabilities adding up to exactly $P(X = x)$, so the first sum is $E[X]$; grouping the second by $y$ gives $E[Y]$.
     $$\sum_{x, y} x \cdot P(X = x, Y = y) = \sum_x x \cdot \underbrace{\sum_y P(X = x, Y = y)}_{P(X = x)} = E[X].$$
6. **It extends to $n$ terms with coefficients**
   - **$E[\sum_i c_i X_i] = \sum_i c_i E[X_i]$** for constants $c_i$: in every row, $\sum_i c_i X_i$ is still each entry times its coefficient, added up.
   - **How to use it**: when the quantity you want is a sum of parts, compute each part's expectation and add them, without caring how the parts depend on each other.

### 1.3 Indicator Variables: The Expectation Is the Probability

**A variable that is 1 when an event happens and 0 otherwise is an indicator; its expectation is the probability of the event.**

1. **The expectation of an indicator**
   - **Definition**: $I_A = [A \text{ happens}]$, so $E[I_A] = 1 \cdot P(A) + 0 \cdot P(\bar A) = P(A)$.
2. **Every count is a sum of indicators**
   - **A count is each candidate contributing 0 or 1**: by linearity, the expected count is the sum over candidates of the probability of being counted.
   - **Example**: the number of fixed points of a random permutation splits into "is position $i$ fixed", each with probability $\frac{1}{n}$, so the expectation is $n \cdot \frac{1}{n} = 1$. The distribution of the count is messy; the expectation takes one line.
3. **When the candidates are symmetric, compute one**
   - **The condition is that every term has the same expectation**: by linearity $E[X_1 + \cdots + X_n] = E[X_1] + \cdots + E[X_n]$, which is $n \cdot E[X_1]$ when the terms share one expectation.
   - **For indicators this becomes two conditions**: each counted term contributes 1, so $E[X_i] = P(\text{counted})$; if the probabilities are also equal, so are the expectations. The expected count is the number of candidates times the probability for one of them.
   - **When a counted term contributes something other than 1, look at the weights**: let every term be counted with probability $p$ and term $i$ contribute $w_i$ when counted; then $E[X_i] = w_i \cdot p$.
     - **Different weights break the shortcut**: the expectations $w_i \cdot p$ differ, so equal probabilities are not enough; add term by term to get $p \cdot \sum_i w_i$.
     - **A common weight $c$ still works**: every term has expectation $c \cdot p$, so the total is $n \cdot c \cdot p$.
   - **Example: scoring the fixed points of a random permutation**: each position is a fixed point with probability $\frac1n$.
     - **A fixed point at position $i$ scores $i$**: the weights differ, and the expectation is $\frac1n \cdot (1 + 2 + \cdots + n) = \frac{n + 1}{2}$.
     - **Every fixed point scores 3**: the weights are equal, and the expectation is $n \cdot 3 \cdot \frac1n = 3$.
   - **Equal probabilities come from a process that treats every position alike**: under a random permutation or a uniform shuffle, relabelling the positions leaves the distribution unchanged, so the event at each position has the same probability.
   - **Independence is not needed**: two neighbouring pairs share a number and are dependent, but linearity does not need independence, so the product still holds.
   - **Example**: for the fixed points above every position has probability $rac{1}{n}$, so only position 1 is computed; for the runs after a shuffle, all $m - 1$ adjacent pairs share one probability, so only one pair is computed (3.2).

### 1.4 Total Expectation: Look at the First Step, Then Average the Rest

**The expectation from state $u$ is, over each possible first step, the probability of that step times "the cost of the step plus the expectation from the next state".**

1. **The recurrence**
   - **Model**: on a directed graph, from $u$ move to $v$ with probability $P_{u,v}$ at cost $w_{u,v}$; stop at a node with no outgoing edges. Let $D_u$ be the total cost from $u$ until stopping.
   - **Formula**:
     $$E[D_u] = \sum_{u \to v} P_{u,v} \bigl(w_{u,v} + E[D_v]\bigr).$$
2. **Why it holds**
   - **Condition on the first step**: given that the first step goes to $v$, $D_u = w_{u,v} + D_v$, and $D_v$ is distributed as a fresh start from $v$.
   - **Expanding is a swap of sums**: $E[D_u] = \sum_d d \sum_v P_{u,v} P(D_v = d - w_{u,v})$; substitute $d' = d - w_{u,v}$ and swap the two sums, and the inner sum is $w_{u,v} + E[D_v]$.
3. **It fixes the direction of expectation DP**
   - **The end is known**: a stopping node has $E[D] = 0$.
   - **Every other node depends on its successors**: so expectation DP usually runs backwards from the end (section 5); when a successor leads back to the node itself, there is a cycle (section 6).

### 1.5 Expectations of Common Distributions

**The geometric distribution's $\frac{1}{p}$ is the one used most: with success probability $p$ per try, you need $\frac{1}{p}$ tries on average.**

| Distribution | Description | Expectation | Variance |
| --- | --- | --- | --- |
| Bernoulli | one trial, 1 on success with probability $p$ | $p$ | $p(1 - p)$ |
| Binomial $B(n, p)$ | successes in $n$ independent trials | $np$ | $np(1 - p)$ |
| Geometric | number of tries until the first success | $\frac{1}{p}$ | $\frac{1 - p}{p^2}$ |
| Discrete uniform | $1 \sim n$ equally likely | $\frac{n + 1}{2}$ | $\frac{n^2 - 1}{12}$ |

1. **The geometric expectation follows from 1.4 in one step**
   - **The first try**: success (probability $p$) ends it; failure (probability $1 - p$) returns to the same state. So $E = 1 + (1 - p) E$, giving $E = \frac{1}{p}$.
   - **The unknown appears on its own right-hand side**: this is the simplest cycle, and the problems in section 6 are all solved by moving terms across like this.
   - **Example**: a password has $N$ equally likely values and is redrawn after each wrong guess; the expected number of guesses is $N$.
2. **The binomial expectation is linearity**
   - **Each of the $n$ trials is a Bernoulli variable**: expectation $p$ each, total $np$, with no binomial coefficients needed.

### 1.6 Printing Modulo $p$: Fractions Become Multiplications by Inverses

**When the answer is "the expectation modulo $p$", write the fraction $\frac{a}{b}$ as $a \cdot b^{-1} \bmod p$; addition, subtraction and multiplication are unchanged, division becomes multiplication by an inverse.**

- **Why it works**: the answer is a rational $\frac{a}{b}$; modulo a prime $p$, $b$ has an inverse, so $\frac{a}{b}$ maps to a unique $a b^{-1}$. The derivation only uses the four operations, so every step can be done modulo $p$.
- **Comparisons cannot be done modulo $p$**: when a strategy takes a max or min of expectations, residues have no order; use floating point, or a fraction class that keeps numerator and denominator (practice 6).

## 2. What Problems It Solves

**Expectation problems fall into six kinds by what is asked: kinds 1 and 2 split directly with no states; kinds 3 to 5 define states and write equations; kind 6 has too many configurations and uses a potential instead.**

1. **The expected number of something: split into indicators**
   - **Signal**: "the expected number of / pairs / runs".
   - **How**: write the count as a sum of 0/1 variables over candidates, compute the probability each one is counted (1.3), and add. With many candidates, those of the same kind share a probability, so multiply by the size of the kind.
   - **Example: runs after a shuffle**: shuffle `1 1 2 2` uniformly, merge adjacent equal numbers into runs, and find the expected number of runs (the full problem is 3.2).
     1. **Computing directly means listing every arrangement**: there are only 6 distinct orders, all equally likely: `1122`, `1212`, `1221`, `2112`, `2121`, `2211`, with 2, 4, 3, 3, 4, 2 runs, average $rac{18}{6} = 3$. With more numbers this list is far too long.
     2. **Split into indicators**: runs = 1 (the first number starts a run) + the number of adjacent pairs that differ, and each of the 3 adjacent pairs (positions 1–2, 2–3, 3–4) contributes a 0 or 1.
     3. **Symmetry: compute one pair**: every adjacent pair differs with the same probability, the probability that two numbers drawn in order from the 4 differ. There are $4 	imes 3 = 12$ ordered draws, $2 + 2 = 4$ of them equal, so the pair differs with probability $rac{8}{12} = rac23$.
     4. **Tied pairs still add**: pairs 1–2 and 2–3 share the second number, so "1–2 differ" and "2–3 differ" affect each other; linearity only needs each pair's own probability (1.2, point 3).
     5. **Add up**: $1 + \frac23 + \frac23 + \frac23 = 3$, matching the list in step 1.
2. **The expected maximum or minimum: go through the distribution function**
   - **Signal**: "the maximum of $n$ draws / the time the last task finishes".
   - **How**: $P(\max = y)$ is awkward, but $P(\max \le y)$ means "every draw is $\le y$", a plain product when draws are independent; take differences to get $P(\max = y)$, or use the tail sum $E[Y] = \sum_{y \ge 1} P(Y \ge y)$ (section 4).
   - **Example: the expected maximum of two rolls of a two-sided die** (the full problem is 4.2).
     1. **"At most" first**: $P(\max \le 1) = \left(\frac12\right)^2 = \frac14$ and $P(\max \le 2) = 1$.
     2. **Take differences**: $P(\max = 1) = \frac14$ and $P(\max = 2) = 1 - \frac14 = \frac34$.
     3. **Weight**: $E = 1 \times \frac14 + 2 \times \frac34 = 1.75$. Counting directly agrees: the four outcomes (1,1), (1,2), (2,1), (2,2) have maxima 1, 2, 2, 2.
3. **The expected number of steps until something happens: geometric distribution or expectation DP**
   - **Signal**: "the expected number of operations until it stops", where each step depends only on the current state.
   - **How**: a constant success probability gives the geometric $\frac{1}{p}$; when it changes with the state, let $E[s]$ be the expected remaining steps from state $s$ and run 1.4 backwards from the end (section 5).
   - **Example: constant success probability, rolling a die until a 6**: each roll succeeds with probability $\frac16$, a geometric distribution, so 6 rolls in expectation.
   - **Example: success probability depends on the state, a bag of coins**: 98 gold, 99 silver and 99 bronze coins; each draw takes one coin, puts it back and adds another of the same kind, stopping when some kind reaches 100. Find the expected number of draws (the full problem is 5.2).
     1. **Define the state**: $E[a][b][c]$ is the expected number of draws left from $(a, b, c)$, and 0 once some kind reaches 100.
     2. **Look at the first draw**: there are 296 coins. Silver or bronze (probability $\frac{198}{296}$) reaches 100 and stops; gold (probability $\frac{98}{296}$) leads to $(99, 99, 99)$, where one more draw always stops, so $E[99][99][99] = 1$.
     3. **Substitute**: $E[98][99][99] = 1 + \frac{98}{296} \times 1 \approx 1.331$.
4. **Expectation with decisions: take the optimum inside the DP**
   - **Signal**: "choose a strategy that minimises / maximises the expectation".
   - **How**: each state takes the best of its options; when only one place changes, the overall change is "probability of reaching that node × change of its expectation" (5.4).
   - **Example: delete one passage to minimise the expected steps**: 4 rooms with a passage $i \to j$ for every $i < j$. Start at 1, take a uniformly random outgoing passage in each room, and stop at 4. One passage may be deleted beforehand; find the minimum expected number of steps (the full problem is 5.4).
     1. **Without deleting, go backwards**: $E_4 = 0$, $E_3 = 1$, $E_2 = 1 + \frac{1 + 0}{2} = 1.5$, $E_1 = 1 + \frac{1.5 + 1 + 0}{3} \approx 1.833$.
     2. **Deleting at room $u$ changes only $E_u$; delete the successor with the largest expectation**: at 1 delete the passage to 2, $E_1' = 1 + \frac{1 + 0}{2} = 1.5$; at 2 delete the passage to 3, $E_2' = 1 + 0 = 1$; room 3 has a single exit and cannot lose it.
     3. **Overall change = probability of reaching $u$ × change of $E_u$**: room 1 is reached with probability 1, giving $1.5$; room 2 with probability $\frac13$, giving $1.833 + \frac13 \times (1 - 1.5) \approx 1.667$. The minimum is 1.5.
5. **States with cycles: write a system of equations**
   - **Signal**: failure sends you back to an earlier state, or a random walk can go back and forth.
   - **How**: one equation per state; eliminate by hand when the structure is simple (6.2, returning to a checkpoint), otherwise use Gaussian elimination ([L2 3.3](/algo/l2-gaussian-elimination/), a random walk on a graph).
   - **Example: failure returns to the checkpoint**: each attempt clears a level with probability $\frac12$; a failure sends you back to level 1 (the only checkpoint). Find the expected number of attempts to clear 2 levels (the full problem is 6.2).
     1. **Clear 1 level**: constant success probability, geometric, $E_1 = 2$.
     2. **Clear 2 levels**: spend $E_1$ attempts on level 1, then try level 2 once; a failure (probability $\frac12$) starts over and needs $E_2$ more. $E_2$ appears on the right: $E_2 = E_1 + 1 + \frac12 E_2$.
     3. **Move it over**: $E_2 = 2(E_1 + 1) = 6$. Continuing the same way, a segment of $L$ levels costs $2^{L+1} - 2$.
6. **Everything changes at random together: find a potential**
   - **Signal**: every round all sets / all elements change at once, and there are far too many configurations to use as states.
   - **How**: give each object a score so that the score of the whole configuration rises by exactly 1 per round in expectation; then the expected number of rounds = final score − initial score (section 7).
   - **Example: random pairing moves elements until one set remains**: two sets with 1 element each. Every round the 2 elements form a pair, and a random one of them moves into the other's set. Find the expected number of rounds until one set remains (the full problem is 7.2).
     1. **Give each set a potential by its size**: a set of size $s$ has potential $f(s)$, chosen so that its expected potential rises by exactly $\frac{s}{N}$ per round (here $N = 2$). The sizes add up to $N$, so the whole configuration rises by exactly 1 per round. An empty set disappears, $f(0) = 0$; also take $f(1) = 0$.
     2. **Write the equation for size 1**: the element is always paired outside; with probability $\frac12$ it leaves (size 0), with probability $\frac12$ the other one comes in (size 2): $\frac12 f(0) + \frac12 f(2) - f(1) = \frac12$, so $f(2) = 1$.
     3. **Expected rounds = final potential − initial potential**: $f(2) - 2 f(1) = 1$. Indeed one round always merges them.

When the question asks for a probability itself, the method is the same as kind 3, storing probabilities instead of expectations.
   - **Example: start at 0, step 1 or 2 cells with equal probability, and find the probability of landing on cell 3**.
     1. **Define the state**: $f[i]$ is the probability of landing on 3 from $i$. $f[3] = 1$; reaching 4 means 3 was skipped, $f[4] = 0$.
     2. **The transition is the average over successors**: $f[i] = \frac12 f[i + 1] + \frac12 f[i + 2]$, computed backwards: $f[2] = \frac12$, $f[1] = \frac12 \times \frac12 + \frac12 \times 1 = \frac34$, $f[0] = \frac12 \times \frac34 + \frac12 \times \frac12 = \frac58$.
     3. **Check by counting**: the walks that land on 3 are 1+1+1, 1+2 and 2+1, with probability $\frac18 + \frac14 + \frac14 = \frac58$.

## 3. Linearity: Split into Indicators

### 3.1 Example: CF 1612E Messages, Contribution per Message

[CF 1612E](https://codeforces.com/problemset/problem/1612/E)

1. **Statement**

   There are $n$ students; student $i$ needs to read message $m_i$ and reads at most $k_i$ messages. You pin $t$ messages: if $t \le k_i$, student $i$ reads all of them; otherwise they read $k_i$ pinned messages chosen uniformly at random. Choose which messages to pin to maximise the expected number of students who read their own message.

   - **Input**: the first line has $n$ ($1 \le n \le 2 \cdot 10^5$); then $n$ lines with $m_i, k_i$ ($1 \le m_i \le 2 \cdot 10^5$, $1 \le k_i \le 20$).
   - **Output**: $t$ on the first line, then $t$ distinct message numbers. Any optimal answer is accepted.

   **Sample 1 input**

   ```text
   3
   10 1
   10 2
   5 2
   ```

   **Sample 1 output**

   ```text
   2
   5 10
   ```

   **Sample 2 input**

   ```text
   3
   10 1
   5 2
   10 1
   ```

   **Sample 2 output**

   ```text
   1
   10
   ```

   **Sample 3 input**

   ```text
   4
   1 1
   2 2
   3 3
   4 4
   ```

   **Sample 3 output**

   ```text
   3
   2 3 4
   ```

   **Sample 4 input**

   ```text
   3
   13 2
   42 2
   37 2
   ```

   **Sample 4 output**

   ```text
   3
   42 13 37
   ```

2. **Idea**
   1. **Split by student into indicators**: the number of readers is $\sum_i [\text{student } i \text{ reads } m_i]$. If $m_i$ is not pinned the probability is 0; if it is, the $\min(k_i, t)$ messages read form a uniform subset of the $t$ pinned ones, so a particular one is read with probability $\frac{\min(k_i, t)}{t}$.
   2. **For a fixed $t$, group by message**: pinning message $x$ contributes $\frac{1}{t} \sum_{m_i = x} \min(k_i, t)$; contributions of different messages do not interact, so take the $t$ largest.
   3. **For $t > 20$ the numerator does not depend on $t$**: since $k_i \le 20$, $\min(k_i, t) = k_i$, and each message has the fixed score $w_x = \sum_{m_i = x} k_i$. Sort by $w$ once and prefix sums give the best value for every $t$. For $t \le 20$, recompute the scores for each $t$.
   4. **Compare $\frac{S_t}{t}$ by cross-multiplying**: $S_t \cdot t' > S_{t'} \cdot t$, no floating point.

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;
   typedef long long ll;

   int main() {
       ios::sync_with_stdio(false);
       cin.tie(nullptr);
       int n;
       cin >> n;
       vector<int> m(n), k(n);
       for (int i = 0; i < n; i++) cin >> m[i] >> k[i];
       vector<int> ids(m);                                  // messages that appear
       sort(ids.begin(), ids.end());
       ids.erase(unique(ids.begin(), ids.end()), ids.end());
       int D = ids.size();
       vector<ll> sc(200001);
       ll bestS = -1;                                       // best expectation is bestS / bestT
       int bestT = 1;
       vector<int> pick;
       auto better = [&](ll S, int t) { return bestS < 0 || S * bestT > bestS * t; };

       // t <= 20: message x scores sum min(k_i, t); take the t largest
       for (int t = 1; t <= min(20, D); t++) {
           for (int x : ids) sc[x] = 0;
           for (int i = 0; i < n; i++) sc[m[i]] += min(k[i], t);
           vector<int> ord = ids;
           partial_sort(ord.begin(), ord.begin() + t, ord.end(), [&](int x, int y) { return sc[x] > sc[y]; });
           ll S = 0;
           for (int j = 0; j < t; j++) S += sc[ord[j]];
           if (better(S, t)) bestS = S, bestT = t, pick.assign(ord.begin(), ord.begin() + t);
       }
       // t > 20: the score is fixed at w_x = sum k_i; sort once, prefix sums give every t
       if (D > 20) {
           for (int x : ids) sc[x] = 0;
           for (int i = 0; i < n; i++) sc[m[i]] += k[i];
           vector<int> ord = ids;
           sort(ord.begin(), ord.end(), [&](int x, int y) { return sc[x] > sc[y]; });
           ll S = 0;
           int bigT = 0;
           for (int t = 1; t <= D; t++) {
               S += sc[ord[t - 1]];
               if (t > 20 && better(S, t)) bestS = S, bestT = t, bigT = t;
           }
           if (bigT) pick.assign(ord.begin(), ord.begin() + bigT);
       }
       cout << bestT << '\n';
       for (int j = 0; j < bestT; j++) cout << pick[j] << " \n"[j + 1 == bestT];
   }
   ```

3. **Cost and pitfalls**
   - **Cost**: $O(20 (n + D \log D))$, where $D$ is the number of distinct messages; each round with $t \le 20$ scans the students and does one partial sort.
   - **Never pin a message nobody needs**: each contribution $\frac{\min(k_i, t)}{t}$ does not increase with $t$, so a zero-score pin never helps and $t$ only goes up to $D$.
   - **Expectations with different denominators cannot be compared directly**: $S_t$ is an integer; cross-multiply $\frac{S_t}{t}$. The largest product is $4 \cdot 10^6 \times 2 \cdot 10^5$, fine for `long long`.

### 3.2 Example: 2026 Jilin Provincial M Crystal Castle, Runs after a Shuffle

[Gym 106567M](https://codeforces.com/gym/106567/problem/M)

1. **Statement**

   A row of $n$ crystals, crystal $i$ has colour $a_i$. Answer $q$ queries $[l, r]$: take out that segment and shuffle it (all distinct colour sequences equally likely); find the expected number of maximal runs of equal colour, modulo 998244353.

   - **Input**: the first line has $T$; each test has $n, q$, then $a_1, \dots, a_n$ ($1 \le a_i \le n$), then $q$ lines $l, r$. The sums of $n$ and of $q$ are each $\le 10^5$.
   - **Output**: one line per query.

   **Sample 1 input**

   ```text {hl_lines=["2-5"]}
   1
   4 2
   1 1 2 2
   1 2
   1 4
   ```

   **Sample 1 output**

   ```text {hl_lines=["1-2"]}
   1
   3
   ```

   **Sample 2 input**

   ```text {hl_lines=["2-8"]}
   1
   10 5
   3 5 3 3 6 4 8 2 3 5
   6 9
   1 8
   8 10
   4 9
   7 7
   ```

   **Sample 2 output**

   ```text {hl_lines=["1-5"]}
   4
   748683272
   3
   665496241
   1
   ```

2. **Idea**
   Let the query length be $m = r - l + 1$ and let colour $c$ appear $\mathit{cnt}_c$ times in it.
   1. **Runs = 1 + the number of adjacent pairs with different colours**: going left to right, each crystal whose colour differs from the previous one starts a new run. Let $R$ be the number of runs and $I_k = [\text{crystals } k \text{ and } k + 1 \text{ differ after the shuffle}]$ for $1 \le k \le m - 1$; in every outcome of the shuffle,
      $$R = 1 + I_1 + I_2 + \cdots + I_{m-1}.$$
   2. **Linearity plus symmetry: compute one pair**: take expectations of both sides, using one property per step:
      $$E[R] \overset{\text{linearity}}{=} 1 + \sum_{k=1}^{m-1} E[I_k] \overset{\text{indicator}}{=} 1 + \sum_{k=1}^{m-1} P(I_k = 1) \overset{\text{symmetry}}{=} 1 + (m - 1)\, P(I_1 = 1).$$
      - **Linearity (1.2)**: $I_1$ and $I_2$ share crystal 2 and are tied together, yet they still split.
      - **Indicator (1.3)**: $I_k$ takes only 0 and 1, so its expectation is the probability that it is 1.
      - **Symmetry (1.3)**: a uniform shuffle treats every position alike, so these $m - 1$ probabilities are all equal to $P(I_1 = 1)$.
   3. **$P(I_1 = 1)$ is the chance that two crystals drawn from the segment differ**: after the shuffle, crystals 1 and 2 are just two crystals drawn in order. There are $m(m - 1)$ ordered draws, of which $S = \sum_c \mathit{cnt}_c (\mathit{cnt}_c - 1)$ have equal colours, so $P(I_1 = 1) = 1 - \frac{S}{m(m - 1)}$. Substituting:
      $$E[\text{runs}] = 1 + (m - 1)\Bigl(1 - \frac{S}{m(m - 1)}\Bigr) = m - \frac{S}{m}.$$
      Query $[1, 4]$ of sample 1 (`1 1 2 2`): $m = 4$, $S = 2 + 2 = 4$, answer $4 - 1 = 3$.
   4. **Queries differ only in $S$; maintain it with Mo's algorithm**: adding a crystal of colour $c$ forms two ordered equal pairs with each existing $c$, so $S$ grows by $2 \mathit{cnt}_c$, then $\mathit{cnt}_c$ grows by 1; removing one decreases $\mathit{cnt}_c$ first, then $S$ by $2 \mathit{cnt}_c$.

   > The essence of expected runs: linearity turns the runs into a sum of the probabilities that each adjacent pair differs, and symmetry makes each of them equal to the probability that two random crystals differ.

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;
   typedef long long ll;
   const ll MOD = 998244353;

   ll pw(ll b, ll e) {
       ll r = 1;
       for (b %= MOD; e; e >>= 1, b = b * b % MOD)
           if (e & 1) r = r * b % MOD;
       return r;
   }

   int main() {
       ios::sync_with_stdio(false);
       cin.tie(nullptr);
       int T;
       cin >> T;
       while (T--) {
           int n, q;
           cin >> n >> q;
           vector<int> a(n + 1);
           for (int i = 1; i <= n; i++) cin >> a[i];
           vector<int> L(q), R(q), ord(q);
           for (int i = 0; i < q; i++) cin >> L[i] >> R[i];
           int B = max(1, (int)(n / sqrt((double)q)));
           iota(ord.begin(), ord.end(), 0);
           sort(ord.begin(), ord.end(), [&](int x, int y) {
               if (L[x] / B != L[y] / B) return L[x] / B < L[y] / B;
               return (L[x] / B) & 1 ? R[x] > R[y] : R[x] < R[y];
           });
           vector<ll> cnt(n + 1, 0);
           ll S = 0;                                     // S = sum_c cnt_c (cnt_c - 1)
           auto ins = [&](int i) { S += 2 * cnt[a[i]]; cnt[a[i]]++; };
           auto del = [&](int i) { cnt[a[i]]--; S -= 2 * cnt[a[i]]; };
           vector<ll> ans(q);
           int cl = 1, cr = 0;
           for (int id : ord) {
               while (cr < R[id]) ins(++cr);
               while (cl > L[id]) ins(--cl);
               while (cr > R[id]) del(cr--);
               while (cl < L[id]) del(cl++);
               ll m = R[id] - L[id] + 1;
               // E = m - S / m
               ans[id] = ((m - S % MOD * pw(m, MOD - 2)) % MOD + MOD) % MOD;
           }
           for (int i = 0; i < q; i++) cout << ans[i] << '\n';
       }
   }
   ```

3. **Cost and pitfalls**
   - **Cost**: $O((n + q)\sqrt{n})$; each pointer move is $O(1)$.
   - **"All distinct colour sequences equally likely"**: crystals of one colour are indistinguishable, but treating them as distinct and shuffling uniformly gives the same distribution of colour sequences, so probabilities can be computed as if all crystals were distinct.
   - **$m = 1$ needs no special case**: $S = 0$ and the answer is 1.

> **When you see "the expectation of some count after a random permutation"**
>
> - **Split into indicators on adjacent positions**: linearity turns the whole expectation into the probability at one position.
> - **The permutation is symmetric, so every position has the same probability**: compute it once and multiply by the number of positions.

## 4. The Distribution Function: Expected Maximum

### 4.1 $P(Y \le y)$ Is Easy; Subtract to Get $P(Y = y)$

**"The maximum equals $y$" needs one draw to hit $y$ exactly and the rest to stay below, which is awkward to count; "the maximum is at most $y$" only needs every draw at most $y$, a plain product for independent draws.**

1. **Take differences**
   - **$P(Y = y) = P(Y \le y) - P(Y \le y - 1)$**: $P(Y \le y)$ is the distribution function.
   - **The distribution function of a maximum**: with $n$ independent draws each $\le y$ with probability $F(y)$, $P(\max \le y) = F(y)^n$. For a minimum, use $P(\min \ge y) = (1 - F(y - 1))^n$.
2. **The tail sum avoids the difference**
   - **For non-negative integer values, $E[Y] = \sum_{y \ge 1} P(Y \ge y)$**: $Y = \sum_{y \ge 1} [Y \ge y]$, and each indicator has expectation $P(Y \ge y)$; this is linearity again.

#### Cost

$O(m \log n)$: $m$ values, each needing one $F(y)^n$ (fast power, $O(\log n)$).

### 4.2 Example: CF 453A Little Pony and Expected Maximum

[CF 453A](https://codeforces.com/problemset/problem/453/A)

1. **Statement**

   An $m$-sided die shows $i$ on face $i$, each face with probability $\frac{1}{m}$. Roll it $n$ times independently and find the expected maximum, with error at most $10^{-4}$.

   - **Input**: one line $m, n$ ($1 \le m, n \le 10^5$).
   - **Output**: a real number.

   **Sample 1 input**

   ```text
   6 1
   ```

   **Sample 1 output**

   ```text
   3.500000000000
   ```

   **Sample 2 input**

   ```text
   6 3
   ```

   **Sample 2 output**

   ```text
   4.958333333333
   ```

   **Sample 3 input**

   ```text
   2 2
   ```

   **Sample 3 output**

   ```text
   1.750000000000
   ```

2. **Idea**
   1. **The probability every roll is $\le y$**: $P(Y \le y) = \left(\frac{y}{m}\right)^n$.
   2. **Take differences for the expectation**:
      $$E[Y] = \sum_{y = 1}^{m} y \left[\left(\frac{y}{m}\right)^n - \left(\frac{y - 1}{m}\right)^n\right].$$
      Sample 3 ($m = 2$, $n = 2$): $1 \times \frac14 + 2 \times \left(1 - \frac14\right) = 1.75$.

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;

   int main() {
       int m, n;
       cin >> m >> n;
       double ans = 0;
       for (int y = 1; y <= m; y++)
           ans += y * (pow((double)y / m, n) - pow((double)(y - 1) / m, n));
       printf("%.12f\n", ans);
   }
   ```

3. **Cost and pitfalls**
   - **Cost**: $O(m \log n)$; `pow` is logarithmic inside.
   - **Do not compute $y^n$ and then divide by $m^n$**: $10^5$ to the power $10^5$ is far beyond `double`; divide first, then raise $\frac{y}{m} \le 1$ to the power.

## 5. Expectation DP: Backwards from the End

> The essence of expectation DP: a state stands for the expected cost still to pay from it until the end; the end is 0, so we work backwards from it.

### 5.1 Define "How Much Is Left from Here"; the End Is 0

**Let $E[s]$ be the expected remaining cost from state $s$; stopping states are 0, and every other state follows from its successors by 1.4; on an acyclic state graph, compute in reverse topological order.**

1. **Why "how much is left"**
   - **The end is known**: nothing more is spent after stopping, so $E = 0$.
   - **The start is not**: pushing forward from the start would also need the probability of reaching each state; backwards only needs the successors' expectations.
2. **The transition is 1.4**
   - **$E[s] = \sum_{s \to s'} P(s \to s') \bigl(\text{cost of the step} + E[s']\bigr)$**: with cost 1 per step, this is the expected number of steps.
3. **When a transition returns to itself, move it across first**
   - **Self-loop**: $E[s] = p \cdot E[s] + (\text{other terms})$ gives $E[s] = \frac{\text{other terms}}{1 - p}$. The geometric distribution (1.5) is exactly this. 5.3 has a self-loop that must be handled separately.

#### Cost

$O(\text{states} \times \text{transitions per state})$, the same as an ordinary DP.

### 5.2 Example: ABC 184D increment of coins

[ABC 184D](https://atcoder.jp/contests/abc184/tasks/abc184_d)

1. **Statement**

   A bag holds $A$ gold, $B$ silver and $C$ copper coins. Each operation draws a coin uniformly at random, puts it back and adds one more of the same kind. Stop when some kind reaches 100 coins; find the expected number of operations, with error at most $10^{-6}$.

   - **Input**: one line $A, B, C$ ($0 \le A, B, C \le 99$, $A + B + C \ge 1$).
   - **Output**: a real number.

   **Sample 1 input**

   ```text
   99 99 99
   ```

   **Sample 1 output**

   ```text
   1.000000000
   ```

   **Sample 2 input**

   ```text
   98 99 99
   ```

   **Sample 2 output**

   ```text
   1.331081081
   ```

   **Sample 3 input**

   ```text
   0 0 1
   ```

   **Sample 3 output**

   ```text
   99.000000000
   ```

   **Sample 4 input**

   ```text
   31 41 59
   ```

   **Sample 4 output**

   ```text
   91.835008202
   ```

2. **Idea**
   1. **The state is the three counts**: $E[a][b][c]$ is the expected remaining number of operations from $(a, b, c)$, and 0 once any count reaches 100.
   2. **Whichever kind is drawn grows by 1**: with $s = a + b + c$,
      $$E[a][b][c] = 1 + \frac{a}{s} E[a + 1][b][c] + \frac{b}{s} E[a][b + 1][c] + \frac{c}{s} E[a][b][c + 1].$$
   3. **Run all three dimensions down from 99**: each state depends only on states with more coins.

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;

   double E[101][101][101];                              // cells with a dimension at 100 stay 0

   int main() {
       int A, B, C;
       cin >> A >> B >> C;
       for (int a = 99; a >= 0; a--)
           for (int b = 99; b >= 0; b--)
               for (int c = 99; c >= 0; c--) {
                   int s = a + b + c;
                   if (s == 0) continue;                 // an empty bag is unreachable
                   E[a][b][c] = 1 + (a * E[a + 1][b][c] + b * E[a][b + 1][c] + c * E[a][b][c + 1]) / s;
               }
       printf("%.9f\n", E[A][B][C]);
   }
   ```

3. **Cost and pitfalls**
   - **Cost**: $O(100^3) = 10^6$.
   - **A kind with 0 coins is never drawn**: $\frac{0}{s}$ is 0 by itself, no special case; only $s = 0$ (all three empty) must be skipped.

### 5.3 Example: CF 908D New Year and Arbitrary Arrangement, Move the Self-Loop Across First

[CF 908D](https://codeforces.com/problemset/problem/908/D)

1. **Statement**

   Given $k, p_a, p_b$. Start with an empty sequence; each second append `a` with probability $\frac{p_a}{p_a + p_b}$, otherwise append `b`. Stop once the sequence has at least $k$ subsequences `ab`. Find the expected number of subsequences `ab` when it stops, modulo $10^9 + 7$.

   - **Input**: one line $k, p_a, p_b$ ($1 \le k \le 1000$, $1 \le p_a, p_b \le 10^6$).
   - **Output**: one integer.

   **Sample 1 input**

   ```text
   1 1 1
   ```

   **Sample 1 output**

   ```text
   2
   ```

   **Sample 2 input**

   ```text
   3 1 4
   ```

   **Sample 2 output**

   ```text
   370000006
   ```

2. **Idea**
   Write $q_a = \frac{p_a}{p_a + p_b}$ and $q_b = 1 - q_a$.
   1. **Two numbers are enough for the state**: $i$ subsequences `ab` so far and $j$ letters `a`. Appending `a` gives $(i, j + 1)$; appending `b` pairs it with every earlier `a`, giving $(i + j, j)$. Let $f(i, j)$ be the expected final count of `ab` from here:
      $$f(i, j) = q_a f(i, j + 1) + q_b f(i + j, j), \qquad i < k.$$
   2. **For $i + j \ge k$ there is a closed form**: the next `b` stops the process, with $i + j + (\text{the number of a's added before it})$ subsequences. The expected number of `a`s before the first `b` is $\frac{q_a}{q_b} = \frac{p_a}{p_b}$ (the geometric expectation minus 1), so $f(i, j) = i + j + \frac{p_a}{p_b}$. This cuts off the otherwise unbounded $j$ at $k$.
   3. **$j = 0$ is a self-loop**: with no `a`, a `b` creates nothing and $(i, 0)$ returns to itself: $f(i, 0) = q_a f(i, 1) + q_b f(i, 0)$, which gives $f(i, 0) = f(i, 1)$. The answer is $f(0, 0) = f(0, 1)$.
   4. **Order of computation**: $f(i, j)$ needs larger $j$ and larger $i$, so run $i$ down from $k - 1$ and $j$ downwards.

   Sample 1 ($k = 1$): $f(0, 0) = f(0, 1) = 0 + 1 + \frac{1}{1} = 2$.

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;
   typedef long long ll;
   const ll MOD = 1e9 + 7;

   ll pw(ll b, ll e) {
       ll r = 1;
       for (b %= MOD; e; e >>= 1, b = b * b % MOD)
           if (e & 1) r = r * b % MOD;
       return r;
   }

   int main() {
       ll k, pa, pb;
       cin >> k >> pa >> pb;
       ll qa = pa * pw(pa + pb, MOD - 2) % MOD, qb = pb * pw(pa + pb, MOD - 2) % MOD;
       ll ab = pa * pw(pb, MOD - 2) % MOD;                  // expected a's before the first b: pa / pb
       vector<vector<ll>> dp(k, vector<ll>(k + 1, 0));
       // i + j >= k: f = i + j + pa / pb
       auto f = [&](ll i, ll j) { return i + j >= k ? (i + j + ab) % MOD : dp[i][j]; };
       for (ll i = k - 1; i >= 0; i--)
           for (ll j = k - 1 - i; j >= 1; j--)
               dp[i][j] = (qa * f(i, j + 1) + qb * f(i + j, j)) % MOD;
       cout << f(0, 1) << '\n';                             // f(0, 0) = f(0, 1)
   }
   ```

3. **Cost and pitfalls**
   - **Cost**: $O(k^2)$.
   - **Without the cut-off the state space is infinite**: $j$ can grow forever by appending `a`; the closed form in step 2 stops it at $i + j \ge k$.
   - **The self-loop cannot go through the transition directly**: at $j = 0$, $f(i + j, j)$ is $f(i, 0)$ itself, not yet computed in the loop order; move it across first to get $f(i, 0) = f(i, 1)$.

### 5.4 Example: ABC 144F Fork in the Road, Removing One Edge Changes One Node

[ABC 144F](https://atcoder.jp/contests/abc144/tasks/abc144_f)

1. **Statement**

   $N$ rooms and $M$ one-way passages, passage $i$ from $s_i$ to $t_i$ ($s_i < t_i$); every room except $N$ has at least one outgoing passage. Starting in room 1, at each room pick an outgoing passage uniformly at random, until reaching $N$. Before starting you may block at most one passage (without making $N$ unreachable). Find the minimum expected number of passages walked, with error at most $10^{-6}$.

   - **Input**: $N, M$ ($2 \le N \le 600$, $N - 1 \le M \le \frac{N(N - 1)}{2}$), then $M$ lines $s_i, t_i$, no duplicates.
   - **Output**: a real number.

   **Sample 1 input**

   ```text
   4 6
   1 4
   2 3
   1 3
   1 2
   3 4
   2 4
   ```

   **Sample 1 output**

   ```text
   1.5000000000
   ```

   **Sample 2 input**

   ```text
   3 2
   1 2
   2 3
   ```

   **Sample 2 output**

   ```text
   2.0000000000
   ```

2. **Idea**
   1. **Without blocking, go backwards**: $E_N = 0$ and $E_u = 1 + \frac{1}{\deg u} \sum_{u \to v} E_v$ for $u$ from $N - 1$ down to 1.
   2. **Blocking an edge out of $u$ changes only $E_u$**: edges go from smaller to larger numbers, so rooms after $u$ never return to $u$ and keep their expectations. $u$ must keep an outgoing edge, so only $\deg u \ge 2$ qualifies, and blocking the successor $v_0$ with the largest expectation is best:
      $$E_u' = 1 + \frac{1}{\deg u - 1}\Bigl(\sum_{u \to v} E_v - E_{v_0}\Bigr).$$
   3. **The change in $E_1$ = probability of reaching $u$ × change in $E_u$**: from room 1, the walk before reaching $u$ never uses $u$'s edges and is unaffected; after reaching $u$ (probability $P_u$) the expectation changes from $E_u$ to $E_u'$. So the new answer is $E_1 + P_u (E_u' - E_u)$. Compute $P_u$ forwards: $P_1 = 1$, $P_v \mathrel{+}= \frac{P_u}{\deg u}$.
   4. **Try every $u$ and take the minimum**: also compare with blocking nothing.

   Sample 1: without blocking, $E_3 = 1$, $E_2 = 1.5$, $E_1 = 1 + \frac{1.5 + 1 + 0}{3} \approx 1.83$; blocking the passage from 1 to 2 gives $E_1' = 1 + \frac{1 + 0}{2} = 1.5$.

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;

   int main() {
       int N, M;
       cin >> N >> M;
       vector<vector<int>> g(N + 1);
       for (int i = 0; i < M; i++) {
           int s, t;
           cin >> s >> t;
           g[s].push_back(t);
       }
       vector<double> E(N + 1, 0), P(N + 1, 0);
       for (int u = N - 1; u >= 1; u--) {                   // expectations, backwards
           for (int v : g[u]) E[u] += E[v];
           E[u] = 1 + E[u] / g[u].size();
       }
       P[1] = 1;                                            // reach probabilities, forwards
       for (int u = 1; u < N; u++)
           for (int v : g[u]) P[v] += P[u] / g[u].size();
       double ans = E[1];
       for (int u = 1; u < N; u++) {
           int d = g[u].size();
           if (d < 2) continue;
           double sum = 0, mx = 0;
           for (int v : g[u]) sum += E[v], mx = max(mx, E[v]);
           // block the successor with the largest E: E_u' = 1 + (sum - mx) / (d - 1); answer moves by P_u (E_u' - E_u)
           ans = min(ans, E[1] + P[u] * (1 + (sum - mx) / (d - 1) - E[u]));
       }
       printf("%.10f\n", ans);
   }
   ```

3. **Cost and pitfalls**
   - **Cost**: $O(N + M)$. Recomputing the whole graph per blocked edge is $O(M^2)$, and per node $O(NM)$; both are slower.
   - **Other nodes keep their expectations only because the graph is acyclic by numbering**: in a graph with cycles, blocking an edge affects every node that can come back to it, and this one-node update does not apply.
   - **A node with one outgoing edge cannot be blocked**: there would be no way out.

> **When you see "change one thing in an expectation DP and find the best"**
>
> - **First ask which states the change affects**: in a DAG, changing $u$'s edges changes only $u$ and the states before it.
> - **Overall change = reach probability × local change**: one forward pass for reach probabilities, then each candidate change is $O(1)$.

## 6. States with Cycles: Write the Equations

### 6.1 Eliminate by Hand If You Can, Otherwise Gaussian Elimination

**When states can return to earlier states, the expectations depend on each other and no computation order exists; write one equation per state and solve them together.**

1. **When the structure is simple, eliminate by hand**
   - **Returns go only to a few fixed states**: for example, failure returns to the most recent checkpoint. Substitute the equations in order so that each expectation becomes "the checkpoint's expectation + a constant"; finally the checkpoint's own equation contains only itself, and moving terms across solves it.
2. **In general, Gaussian elimination**
   - **$n$ states, $n$ equations**: $E_u - \sum_v P_{u,v} E_v = c_u$, with $E = 0$ at the end. Over the reals this is $O(n^3)$, fine for a few hundred states.
   - **Example**: a random walk on a graph, [L2 3.3 Luogu P3232](/algo/l2-gaussian-elimination/); the modular version is in L2 section 4.

### 6.2 Example: CF 1453D Checkpoints, Returning to a Checkpoint Costs $2^{L+1} - 2$

[CF 1453D](https://codeforces.com/problemset/problem/1453/D)

1. **Statement**

   A game has $n$ stages played in order from stage 1. Each stage may have a checkpoint, and stage 1 always does. Each try of a stage succeeds with probability $\frac12$ and moves to the next stage; a failure returns to the most recent checkpoint passed. Build at most 2000 stages and choose the checkpoints so that the expected number of tries to finish is exactly $k$, or print $-1$ if impossible.

   - **Input**: $t$ ($1 \le t \le 50$), then one line $k$ per test ($1 \le k \le 10^{18}$).
   - **Output**: for each test, $-1$, or two lines: the number of stages $n$ and $n$ values 0/1 marking checkpoints (the first must be 1). Any valid answer is accepted.

   **Sample 1 input**

   ```text {hl_lines=[2,4]}
   4
   1
   2
   8
   12
   ```

   **Sample 1 output**

   ```text {hl_lines=[1,"4-5"]}
   -1
   1
   1
   4
   1 1 1 1
   5
   1 1 0 1 1
   ```

2. **Idea**
   1. **Checkpoints cut the stages into independent blocks**: once past the next checkpoint, you never return to this block, so the total expectation is the sum over blocks.
   2. **A block of $L$ stages (checkpoint only at its start) costs $E_L = 2^{L+1} - 2$**: to clear $L$ stages, first clear $L - 1$ ($E_{L-1}$ tries), then try stage $L$ once: success ends it, failure (probability $\frac12$) restarts the block. $E_L$ appears on the right again:
      $$E_L = E_{L-1} + 1 + \tfrac12 E_L \implies E_L = 2 E_{L-1} + 2.$$
      $E_1 = 2$, so $E_L = 2^{L+1} - 2$: 2, 6, 14, 30, …
   3. **Every block is even, so odd $k$ is impossible**: for even $k$, go greedily from large to small, each time taking the largest $L$ with $2^{L+1} - 2 \le k$.
   4. **The length fits**: after taking $L$, what remains is below $2^{L+1}$, so the next $L$ is no larger and can equal $L$ at most once. For $k \le 10^{18}$, $L \le 58$, and the total is at most $58 + 57 + \cdots + 1 + 58 < 2000$.

   For $k = 8$: take $L = 2$ (6), then 2 with $L = 1$, printing `1 0 1`; it differs from the sample's `1 1 1 1` and both are correct.

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;
   typedef long long ll;

   int main() {
       int t;
       cin >> t;
       while (t--) {
           ll k;
           cin >> k;
           if (k & 1) {
               cout << -1 << '\n';
               continue;
           }
           vector<int> st;
           while (k > 0) {
               int L = 1;                                   // largest L with 2^(L+1) - 2 <= k
               while ((1LL << (L + 2)) - 2 <= k) L++;
               k -= (1LL << (L + 1)) - 2;
               st.push_back(1);
               for (int i = 1; i < L; i++) st.push_back(0);
           }
           cout << st.size() << '\n';
           for (size_t i = 0; i < st.size(); i++) cout << st[i] << " \n"[i + 1 == st.size()];
       }
   }
   ```

3. **Cost and pitfalls**
   - **Cost**: $O(\log^2 k)$ per test.
   - **$k = 1$ is impossible**: the shortest block already costs 2.
   - **Do not build from small blocks up**: using only $L = 1$ needs $k / 2$ stages, far beyond 2000 for $k$ up to $10^{18}$.

## 7. A Potential: Rising by Exactly 1 per Round in Expectation

### 7.1 Choose a Potential So That the Expected Number of Rounds Is a Difference

**When there are too many configurations to use as states, give each object a score $f$ so that the total score $\Phi$ of the configuration rises by exactly 1 per round in expectation; then the expected number of rounds is the final $\Phi$ minus the initial $\Phi$.**

1. **Why it works**
   - **$\Phi$ rises by 1 per round on average**: from start to finish, the average rise of $\Phi$ equals the average number of rounds. The final configuration is unique (for example "one set left"), so its $\Phi$ is a constant and $E[\text{rounds}] = \Phi_{\text{final}} - \Phi_{\text{initial}}$. In probability theory this is the optional stopping theorem for martingales.
2. **Split the "+1" among the objects**
   - **$\Phi$ is the sum of the objects' scores**: by linearity, $E[\text{new } \Phi]$ is the sum of each object's expected new score.
   - **When each object's change depends only on itself, one dimension is left**: give an object of size $s$ the share $\frac{s}{N}$ ($N$ is the total size), so the shares add up to exactly 1. It is then enough that $E[f(s')] - f(s) = \frac{s}{N}$ for every $s$, with unknowns $f(1), \dots, f(N)$.
3. **Solve the system**
   - **$N$ unknowns, $N - 1$ equations**: with $f$ solved, the answer is $f(N) - \sum f(\text{initial object sizes})$. The missing equation is a degree of freedom; add $f(1) = 0$. Without special structure, use Gaussian elimination.

#### Cost

$O(N^3)$: building the equations is $O(N^3)$ with a small constant, Gaussian elimination is $O(N^3)$, where $N$ is the total size.

### 7.2 Example: 2025 CCPC Harbin H How Many Rounds Are Expected?

Problem H of the 11th CCPC Harbin site; 9 of 278 teams solved it in the contest.

1. **Statement**

   There are $n$ sets; set $i$ has $a_i$ elements, $2m$ distinct elements in total ($\sum a_i = 2m$). Each round, the $2m$ elements are paired uniformly at random into $m$ pairs; in each pair, one element chosen at random moves into the set of its partner. Find the expected number of rounds until all elements are in one set, modulo 998244353.

   - **Input**: $t$ ($1 \le t \le 100$). Each test has $n, m$ ($1 \le n \le 2m \le 400$), then $a_1, \dots, a_n$ ($\sum a_i = 2m$). The sum of $n$ is at most 800 and the sum of $m$ at most 400.
   - **Output**: one line per test.

   **Sample 1 input**

   ```text {hl_lines=["2-3","6-7"]}
   4
   2 1
   1 1
   2 2
   2 2
   2 2
   1 3
   3 2
   1 1 2
   ```

   **Sample 1 output**

   ```text {hl_lines=[1,3]}
   1
   3
   499122179
   499122180
   ```

   **Sample 2 input**

   ```text {hl_lines=["2-3","6-7"]}
   3
   6 5
   2 1 1 3 1 2
   10 100
   90 12 18 1 1 24 7 4 37 6
   10 200
   102 19 25 11 43 97 19 28 11 45
   ```

   **Sample 2 output**

   ```text {hl_lines=[1,3]}
   347465837
   225202828
   437065763
   ```

2. **Idea**
   Write $N = 2m$.
   1. **A set's new size depends only on its own size**: for a set of size $s$, a pair inside the set stays inside however it moves; a pair crossing the boundary loses an element ($-1$) or gains one ($+1$) with probability one half each. The distribution of "how many elements are paired outside" depends only on $s$ and $N$.
   2. **Apply 7.1**: the equations are $E[f(s')] - f(s) = \frac{s}{N}$ for $s = 1, \dots, N - 1$; an emptied set disappears, so $f(0) = 0$; the answer is $f(N) - \sum f(a_i)$.
   3. **The distribution of $s'$**: let $k$ elements be paired outside ($s - k$ even). Choosing $k$ inside, $k$ outside and matching them gives $\binom{s}{k}\binom{N - s}{k} k!$ ways; the rest pair up within each side. With $p(x)$ the number of perfect matchings on $x$ points ($p(x) = (x - 1)(x - 3) \cdots 1$, $p(0) = 1$):
      $$P(k) = \frac{\binom{s}{k}\binom{N - s}{k}\, k!\; p(s - k)\; p(N - s - k)}{p(N)}.$$
      If $j$ of those $k$ pairs move an outside element in, $s' = s - k + 2j$, with probability $\frac{\binom{k}{j}}{2^k}$.
   4. **Add $f(1) = 0$**: the expectation of $s'$ is $s$, so $f(s) + \lambda s$ satisfies every equation too, and since the set sizes always add up to $N$, $\lambda$ cancels in the answer.

   Sample $[2, 2]$ ($N = 4$): for $s = 1$, $s'$ is 0 or 2, so $\frac12 f(2) - f(1) = \frac14$ and $f(2) = \frac12$; for $s = 2$, $P(k = 0) = \frac13$ and $P(k = 2) = \frac23$, so $\frac13 f(2) + \frac23 \bigl(\frac12 f(2) + \frac14 f(4)\bigr) - f(2) = \frac12$ and $f(4) = 4$. The answer is $4 - 2 \times \frac12 = 3$.

   > The essence of expected rounds: find a potential that rises by exactly 1 per round in expectation; the expected number of rounds is the final potential minus the initial one.

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;
   typedef long long ll;

   // gauss (modulo a prime) from L2 4.1 with P changed to 998244353; declarations only, copy the implementation from L2
   const ll P = 998244353;
   ll qp(ll a, ll e);
   int gauss(vector<vector<ll>>& a, int m, vector<int>& where);

   int main() {
       ios::sync_with_stdio(false);
       cin.tie(nullptr);
       const int MX = 405;
       vector<ll> fact(MX), ifact(MX), pm(MX, 0), ip2(MX);
       fact[0] = 1;
       for (int i = 1; i < MX; i++) fact[i] = fact[i - 1] * i % P;
       ifact[MX - 1] = qp(fact[MX - 1], P - 2);
       for (int i = MX - 1; i > 0; i--) ifact[i - 1] = ifact[i] * i % P;
       pm[0] = 1;                                           // pm[x]: perfect matchings on x points
       for (int x = 2; x < MX; x += 2) pm[x] = pm[x - 2] * (x - 1) % P;
       ip2[0] = 1;
       for (int i = 1; i < MX; i++) ip2[i] = ip2[i - 1] * ((P + 1) / 2) % P;
       auto C = [&](int a, int b) -> ll { return fact[a] * ifact[b] % P * ifact[a - b] % P; };

       int t;
       cin >> t;
       while (t--) {
           int n, m;
           cin >> n >> m;
           vector<int> a(n);
           for (auto& x : a) cin >> x;
           int N = 2 * m;
           // unknowns f(1..N) in columns 0..N-1, column N is the right-hand side
           vector<vector<ll>> A(N, vector<ll>(N + 1, 0));
           A[0][0] = 1;                                     // row 0: f(1) = 0
           ll invPm = qp(pm[N], P - 2), invN = qp(N, P - 2);
           for (int s = 1; s < N; s++) {                    // row s: E[f(s')] - f(s) = s / N
               for (int k = s % 2; k <= min(s, N - s); k += 2) {
                   ll p = C(s, k) * C(N - s, k) % P * fact[k] % P * pm[s - k] % P * pm[N - s - k] % P * invPm % P;
                   for (int j = 0; j <= k; j++) {           // s' = s - k + 2j with probability C(k, j) / 2^k
                       int x = s - k + 2 * j;
                       if (x > 0) A[s][x - 1] = (A[s][x - 1] + p * C(k, j) % P * ip2[k]) % P;
                   }
               }
               A[s][s - 1] = (A[s][s - 1] + P - 1) % P;
               A[s][N] = s * invN % P;
           }
           vector<int> where;
           gauss(A, N, where);                              // unique after adding f(1) = 0
           auto f = [&](int x) { return A[where[x - 1]][N]; };
           ll ans = f(N);
           for (int x : a) ans = (ans - f(x) + P) % P;
           cout << ans << '\n';
       }
   }
   ```

3. **Cost and pitfalls**
   - **Cost**: $O(N^3)$ with $N \le 400$.
   - **$f(0) = 0$ is not an unknown**: an emptied set is no longer part of the configuration, so the term moving to size 0 is dropped.
   - **One equation short is not a bug in the problem**: every $f(s) + \lambda s$ is a solution; $f(1) = 0$ pins it down.
   - **Count pairings as perfect matchings**: all elements are paired at once into $m$ pairs, not each choosing a partner independently; the denominator is $p(N) = (N - 1)!!$.

> **When you see "a random process; find the expected number of rounds until it ends"**
>
> - **Look for a potential that rises by exactly 1 per round in expectation**: expected rounds = final potential − initial potential, with no need to treat whole configurations as states.
> - **Split the potential by object**: when each object's change depends only on itself, the equations have only the object's size as a dimension.

## 8. Techniques for Deriving the Formulas

**Write the equation by looking at the first step, then simplify by splitting contributions and moving terms across; squares, phases and step counts each have a standard form.**

### 8.1 Four Already Used Above

1. **Look at the first step; the end state is 0**: $E[s] = 1 + \sum_{s'} P(s \to s') E[s']$, computed backwards from the end (1.4, 5.1).
2. **When the unknown reappears on the right, move it over**: $E = a + pE$ gives $E = \frac{a}{1 - p}$ (the self-loop in 5.3, the checkpoint in 6.2).
3. **Split into indicators and compute one when symmetric**: the condition is that every term has the same expectation (1.3, 3.2).
4. **For extremes, find "at most" first, then take differences**: $P(\max \le y)$ is a product for independent draws (4.1).

### 8.2 An Expectation Cannot Be Squared Directly: Track Several Moments

**$E[x^2] \ne E[x]^2$; to get the expectation of $x^2$, carry $E[x]$ and $E[x^2]$ through the recurrence together.**

1. **Principle**
   - **Expanding leaves only lower moments**: when $x$ becomes $x + 1$, $(x + 1)^2 = x^2 + 2x + 1$, so $E[(x + 1)^2] = E[x^2] + 2E[x] + 1$. Cubes work the same way: $E[(x + 1)^3] = E[x^3] + 3E[x^2] + 3E[x] + 1$.
   - **The square of a count splits into pairs**: $\left(\sum_i I_i\right)^2 = \sum_i \sum_j I_i I_j$, so $E[X^2] = \sum_i \sum_j P(I_i = I_j = 1)$.
   - **Example**: toss $n$ coins and let $X$ be the number of heads. The $n$ terms with $i = j$ have probability $\frac12$; the $n(n - 1)$ terms with $i \ne j$ have probability $\frac14$. $E[X^2] = \frac{n}{2} + \frac{n(n - 1)}{4} = \frac{n(n + 1)}{4}$. For $n = 2$ the four outcomes give $X^2$ = 0, 1, 1, 4, averaging $1.5$, which matches, while $E[X]^2 = 1$.
2. **Example: Luogu P1654 OSU!, the cube of run lengths**
   1. **Statement**

      There are $n$ independent operations; operation $i$ succeeds with probability $p_i$. Write the results as a 0/1 string; every maximal run of $x$ ones scores $x^3$. Output the expected total score to one decimal place.

      - **Input**: $n$ on the first line ($1 \le n \le 10^5$), then $n$ reals $p_i$ ($0 \le p_i \le 1$).
      - **Output**: one real number.

      **Sample input**

      ```text
      3
      0.5 0.5 0.5
      ```

      **Sample output**

      ```text
      6.0
      ```

   2. **Idea**
      1. **Let $x_i$ be the length of the run of ones ending at position $i$**: $x_i = x_{i-1} + 1$ on success and $0$ on failure.
      2. **Carry the first and second moments together**: let $a_i = E[x_i]$ and $b_i = E[x_i^2]$. Only success (probability $p_i$) is non-zero:
         $$a_i = p_i (a_{i-1} + 1), \qquad b_i = p_i (b_{i-1} + 2a_{i-1} + 1).$$
      3. **Split the score by how much position $i$ adds**: a run growing from $x$ to $x + 1$ adds $(x + 1)^3 - x^3 = 3x^2 + 3x + 1$. By linearity, position $i$ adds $p_i (3b_{i-1} + 3a_{i-1} + 1)$ in expectation.
      4. **Sample**: position 1 adds $\frac12$, with $a_1 = b_1 = \frac12$; position 2 adds $\frac12(1.5 + 1.5 + 1) = 2$, with $a_2 = 0.75$, $b_2 = 1.25$; position 3 adds $\frac12(3.75 + 2.25 + 1) = 3.5$. Total $0.5 + 2 + 3.5 = 6$.

      ```cpp
      #include <bits/stdc++.h>
      using namespace std;

      int main() {
          ios::sync_with_stdio(false);
          cin.tie(nullptr);
          int n;
          cin >> n;
          double a = 0, b = 0, ans = 0;             // a = E[x], b = E[x^2], x = length of the run of ones ending here
          for (int i = 0; i < n; i++) {
              double p;
              cin >> p;
              ans += p * (3 * b + 3 * a + 1);       // (x + 1)^3 - x^3 = 3x^2 + 3x + 1
              b = p * (b + 2 * a + 1);
              a = p * (a + 1);
          }
          printf("%.1f\n", ans);
      }
      ```

   3. **Complexity and pitfalls**
      - **Complexity**: $O(n)$.
      - **Update $b$ before $a$**: $b_i$ uses $a_{i-1}$.
      - **$a^3$ is not $E[x^3]$**: in the sample, $a_3 = 0.875$ and $a_3^3 \approx 0.67$, while the true $E[x_3^3] = \frac18 \cdot 27 + \frac18 \cdot 8 + \frac14 \cdot 1 = 4.625$.

### 8.3 Phases: Each One Is Geometric

**When the process splits by progress into phases with a constant success probability inside each, each phase costs $\frac{1}{p}$ in expectation and the total is the sum.**

1. **Why the phases add**: the total count is the sum of the phase counts, so by linearity the expectations add; the phases need not be independent.
2. **Example: collect all $n$ kinds of cards, each draw a uniformly random kind; find the expected number of draws**
   1. **Phase by how many kinds you have**: with $k$ kinds, a draw is new with probability $\frac{n - k}{n}$, so the phase costs $\frac{n}{n - k}$ draws.
   2. **Add up**: $\sum_{k=0}^{n-1} \frac{n}{n - k} = n\left(1 + \frac12 + \cdots + \frac1n\right)$.
   3. **Small case**: for $n = 2$ the first card is always new (1 draw) and the second kind comes with probability $\frac12$ (2 draws expected), 3 in total; the formula gives $2 \times (1 + \frac12) = 3$.

### 8.4 Counting Steps: Use the Tail Sum

**When "stops exactly at step $t$" is awkward but "has not stopped after $t$ steps" is easy, use $E[T] = \sum_{t \ge 0} P(T > t)$.**

1. **Why it holds**: $T = \sum_{t \ge 0} [T > t]$ (exactly $T$ values of $t$ satisfy $T > t$); take expectations, and each term is a probability.
2. **Example: $n$ lamps; every round each unlit lamp lights with probability $p$ and stays lit; find the expected number of rounds until all are lit**
   1. **Not all lit after $t$ rounds**: one lamp is still dark after $t$ rounds with probability $(1 - p)^t$, so $P(T > t) = 1 - \bigl(1 - (1 - p)^t\bigr)^n$.
   2. **Plug into the tail sum**: for $n = 2$, $p = \frac12$, $P(T > t) = 2 \cdot 2^{-t} - 4^{-t}$, which sums to $2 \times 2 - \frac43 = \frac83$.
   3. **Check another way**: each lamp alone is geometric with expectation 2; at least one lights in a round with probability $\frac34$, so the first one takes $\frac43$ rounds in expectation. $E[\max] = E[a] + E[b] - E[\min] = 2 + 2 - \frac43 = \frac83$, which matches.

### 8.5 Easy Places to Go Wrong

**Linearity holds for any random variables, but expectations cannot be pushed through products, ratios or extremes.**

1. **$E[XY] = E[X] \cdot E[Y]$ needs independence**: with $X = Y$ = "one coin shows heads", $E[XY] = E[X] = \frac12$ while $E[X] \cdot E[Y] = \frac14$.
2. **$E\left[\frac{X}{Y}\right] \ne \frac{E[X]}{E[Y]}$**: with $Y$ equal to 1 or 2 with equal probability, $E\left[\frac{1}{Y}\right] = \frac34$ while $\frac{1}{E[Y]} = \frac23$.
3. **$E[\max] \ne \max(E)$**: for two coins taking 0 or 1, $E[\max] = \frac34$ while both expectations are $\frac12$. Extremes go through the distribution as in section 4.
4. **Check with $n = 1, 2$ by hand**: with few cases, list every outcome and average, and write code only once the formula matches.

## Practice

Each problem lists the sections it uses.

**Required**

1. [Luogu P1297](https://www.luogu.com.cn/problem/P1297): "question $i$'s answer happens to match" is an indicator with probability $\frac{1}{\max(a_i, a_{i+1})}$. Section 3.
2. [CF 280C Game on Tree](https://codeforces.com/problemset/problem/280/C): "node $v$ is chosen itself" is an indicator with probability $\frac{1}{\text{depth}}$. Section 3.
3. [Luogu P4316](https://www.luogu.com.cn/problem/P4316): the expected length of a walk to the end of a DAG, the template problem for 5.1.
4. [CF 1626F A Random Code Problem](https://codeforces.com/problemset/problem/1626/F): split the answer over elements by linearity; split each element into a multiple of $L = \operatorname{lcm}(1..16)$, which the mods never touch and is computed directly, and a remainder, handled by a DP over values. Sections 3 and 5.

**Optional**

5. [Nowcoder 108215I](https://ac.nowcoder.com/acm/contest/108215/I): the expected number of draws to complete seven pairs; the state only needs "cards left in the wall, pairs already held". Section 5.
6. [Gym 105358L](https://codeforces.com/gym/105358/problem/L): refreshing a timer to minimise expected penalty; the best strategy is a threshold, whose expectation $\frac{c - 1}{2} + \frac{T}{c}$ is minimised near $\sqrt{2T}$; the answer must be a reduced fraction, so use a fraction class. Sections 1.5 and 1.6.
7. [Luogu P2973](https://www.luogu.com.cn/problem/P2973): a random walk on a graph with cycles, Gaussian elimination. Section 6.
8. [Nowcoder 11183F](https://ac.nowcoder.com/acm/contest/11183/F): sentences written at random; the probability that a string appears, a probability DP on the KMP automaton. End of section 2.
9. [Luogu P1365 WJMZBMR osu! / Easy](https://www.luogu.com.cn/problem/P1365): each `?` is `o` or `x` with probability one half; the expected sum of squared lengths of runs of `o`, the second-order version of 8.2, which tracks only $E[x]$. Section 8.2.

## Related Posts

- [L2 Gaussian Elimination](/algo/l2-gaussian-elimination/): how to solve the cyclic systems of section 6; 3.3 is a complete random-walk example, and section 4 is the modular template used in 7.2.
- [C0 Contest Math Overview](/algo/c0-contest-math-overview/): 3.8 is the one-paragraph version of this post, and min-max inversion at the end of 3.5 gives the expected time until everything has appeared.
