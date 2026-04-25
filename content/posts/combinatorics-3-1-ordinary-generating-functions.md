---
title: "Combinatorics #3.1: Ordinary Generating Functions"
date: 2026-04-25
slug: "combinatorics-3-1-ordinary-generating-functions"
description: "Formal power series basics, ordinary generating functions, inversion identities, generalized binomial expansions, bounded counting examples, and recurrence-to-closed-form examples such as Fibonacci and Catalan."
summary: "Formal power series basics, ordinary generating functions, inversion identities, generalized binomial expansions, bounded counting examples, and recurrence-to-closed-form examples such as Fibonacci and Catalan."
categories: [Combinatorics]
tags: [math, combinatorics, generating-function, ogf, recurrence, catalan, diophantine-equations]
math: true
toc: true
---

Reference: [Combinatorics #1.1: Permutations and Combinations](/posts/combinatorics-1-1-permutations-combinations/)

Suppose $f(n)$ is the number of positive integer solutions to

$$
x+y+z\le n.
$$

Then we get a sequence

$$
f(0),f(1),f(2),\dots
$$

To study a sequence $\{a_n\}$ efficiently, we often attach to it a **generating function**, or more precisely a formal power series:

$$
G(x)=\sum_{n=0}^{\infty} a_n x^n.
$$

By studying algebraic properties of $G(x)$, such as differentiation, multiplication by polynomials, or partial fraction decomposition, we can derive recurrence relations, summation formulas, and closed forms.

---

# 1 Formal Power Series and OGF

## 1.1 Polynomials and formal power series

$$
\begin{array}{l}
\bullet\ \text{Polynomial:}\ A(x)=\sum_{i=0}^{n} a_i x^i \\
\bullet\ \text{Formal power series:}\ A(x)=\sum_{i\ge 0} a_i x^i
\end{array}
$$

Here $a_i$ lies in a field $K$, usually $\mathbb{R}$ or $\mathbb{Z}_p$.

The key point is that in a formal power series, $x$ is just a symbol. We do **not** care about convergence. We only use algebraic manipulation.

## 1.2 Operations

Let

$$
A(x)=\sum_{i\ge 0} a_i x^i,\qquad
B(x)=\sum_{i\ge 0} b_i x^i.
$$

Then:

- Addition:
  $$
  A(x)+B(x)=\sum_{i\ge 0}(a_i+b_i)x^i
  $$
- Subtraction:
  $$
  A(x)-B(x)=\sum_{i\ge 0}(a_i-b_i)x^i
  $$
- Multiplication:
  $$
  A(x)B(x)=\sum_{k\ge 0}\left(\sum_{i+j=k} a_i b_j\right)x^k
  $$

So formal power series form a ring under $+$, $-$, and $\times$.

Written coefficient-wise,

$$
A(x)B(x)
=a_0b_0+(a_0b_1+a_1b_0)x+(a_0b_2+a_1b_1+a_2b_0)x^2+\cdots.
$$

This is exactly the discrete convolution of the coefficient sequences. If

$$
c_k=\sum_{i+j=k} a_i b_j,
$$

then

$$
A(x)B(x)=\sum_{k\ge 0} c_k x^k.
$$

Notation:

$$
[x^n]A(x)
$$

means the coefficient of $x^n$ in $A(x)$.

## 1.3 Definition of OGF

The **ordinary generating function** of a sequence $\{a_n\}$ is

$$
A(x)=\sum_{n\ge 0} a_n x^n.
$$

## 1.4 Example: counting bounded solutions

Consider the number of integer solutions of

$$
x_1+x_2+\cdots+x_k=n,
\qquad
l_i\le x_i\le r_i \quad (1\le i\le k).
$$

The generating-function method is useful because it adapts easily. For example, if we want the number of positive integer solutions of

$$
x_1+2x_2+3x_3=n,
$$

then we can write

$$
\begin{aligned}
F_1(x) &= \sum_{i\ge 1}x^i=x+x^2+x^3+\cdots, \\
F_2(x) &= \sum_{\substack{i\ge 1\\2\mid i}}x^i=x^2+x^4+x^6+\cdots, \\
F_3(x) &= \sum_{\substack{i\ge 1\\3\mid i}}x^i=x^3+x^6+x^9+\cdots.
\end{aligned}
$$

Then the answer is obtained by extracting a coefficient from the product.

## 1.5 Standard OGF pattern

Let $S=\{a_1,a_2,\dots,a_k\}$, and suppose the set of allowed multiplicities of $a_i$ is $M_i$.
Define

$$
F_i(x)=\sum_{u\in M_i}x^u.
$$

If $g(n)$ is the number of ways to choose $n$ elements from $S$ to form a multiset, then

$$
G(x)=\sum_{n\ge 0} g(n)x^n
$$

satisfies

$$
G(x)=F_1(x)F_2(x)\cdots F_k(x).
$$

---

# 2 Closed Forms and Inversion

The main philosophy is to turn a counting problem into an algebra problem on formal power series.

## 2.1 Identity and inverse

The multiplicative identity is

$$
e(x)=1.
$$

Since we are working in a ring, not every nonzero series is invertible.

A multiplicative inverse of $A(x)$ is a series $B(x)$ such that

$$
A(x)B(x)=1.
$$

Such an inverse exists whenever the constant term is nonzero:

$$
[x^0]A(x)\neq 0.
$$

### Brute-force inverse in $O(n^2)$

Let

$$
\begin{aligned}
A(x)&=a_0+a_1x+a_2x^2+\cdots+a_nx^n+\cdots, \\
B(x)&=b_0+b_1x+b_2x^2+\cdots+b_nx^n+\cdots.
\end{aligned}
$$

Then

$$
A(x)B(x)=a_0b_0+(a_0b_1+a_1b_0)x+(a_0b_2+a_1b_1+a_2b_0)x^2+\cdots.
$$

If we require

$$
A(x)B(x)=1+0x+0x^2+\cdots,
$$

then coefficient matching gives:

- constant term:
  $$
  a_0b_0=1 \Rightarrow b_0=a_0^{-1}
  $$
- linear term:
  $$
  a_0b_1+a_1b_0=0 \Rightarrow b_1=-a_1b_0\cdot a_0^{-1}
  $$
- quadratic term:
  $$
  a_0b_2+a_1b_1+a_2b_0=0
  $$
- in general:
  $$
  b_n=-(a_1b_{n-1}+a_2b_{n-2}+\cdots+a_nb_0)\cdot a_0^{-1}.
  $$

So the straightforward recurrence computes the inverse in $O(n^2)$ time.

## 2.2 Common inverse formulas

1. Geometric series:
   $$
   \frac{1}{1-x}=\sum_{i\ge 0}x^i
   $$

2. Scaled geometric series:
   $$
   \frac{1}{1-ax}=\sum_{i\ge 0}a^i x^i
   $$

3. Higher-power version:
   $$
   \frac{1}{(1-x)^k}=\sum_{i\ge 0}\binom{i+k-1}{i}x^i
   $$

Also,

$$
1+f(x)+f(x)^2+\cdots=\frac{1}{1-f(x)}.
$$

And

$$
(1+x+x^2+\cdots)^k=\sum_{n\ge 0}\binom{n+k-1}{k-1}x^n.
$$

Its combinatorial meaning is

$$
[x^n]\frac{1}{(1-x)^k}
=\binom{n+k-1}{n}
=\binom{n+k-1}{k-1},
$$

which counts the number of nonnegative integer solutions of

$$
x_1+x_2+\cdots+x_k=n,\qquad x_i\ge 0.
$$

## 2.3 A compact formula list

1. Period-$k$ ones:
   $$
   \sum_{i\ge 0}x^{ki}=\frac{1}{1-x^k}
   \quad\Longrightarrow\quad
   \langle 1,0,\dots,0,1,0,\dots,0,1,0,\dots\rangle
   $$

2. Finite truncated version:
   $$
   \sum_{i=0}^{n}x^{ki}=\frac{1-x^{k(n+1)}}{1-x^k}
   $$

3. Binomial theorem:
   $$
   \sum_{i=0}^{n}\binom{n}{i}x^i=(1+x)^n
   $$

4. Weighted binomial theorem:
   $$
   \sum_{i=0}^{n}\binom{n}{i}p^ix^i=(1+px)^n
   $$

5. Geometric progression:
   $$
   \sum_{i\ge 0}p^ix^i=\frac{1}{1-px}
   \quad\Longrightarrow\quad
   \langle 1,p,p^2,p^3,\dots\rangle
   $$

6. Positive integers only:
   $$
   \sum_{i\ge 1}x^i=\frac{x}{1-x}
   \quad\Longrightarrow\quad
   \langle 0,1,1,1,\dots\rangle
   $$

7. Arithmetic progression coefficients:
   $$
   \sum_{i\ge 0}(i+1)x^i=\frac{1}{(1-x)^2}
   $$

8. Another standard expansion:
   $$
   \sum_{i\ge 0}\binom{n+i}{i}x^i=\frac{1}{(1-x)^{n+1}}.
   $$

## 2.4 Generalized binomial theorem

When a generating function simplifies to a numerator over a single denominator, we often need

$$
(x+y)^\alpha=\sum_{i=0}^{\infty}\binom{\alpha}{i}x^{\alpha-i}y^i.
$$

Here $\alpha$ can be any real number, including negative and fractional values, and

$$
\binom{\alpha}{i}
=\frac{\alpha^{\underline{i}}}{i!}
=\frac{\alpha(\alpha-1)(\alpha-2)\cdots(\alpha-i+1)}{i!}.
$$

For example, when $\alpha\lt 0$:

$$
\begin{aligned}
\frac{1}{(1-x)^k}
&=(1-x)^{-k} \\
&=\sum_{j=0}^{\infty}\binom{-k}{j}(-x)^j \\
&=\sum_{j=0}^{\infty}\frac{k(k+1)(k+2)\cdots(k+j-1)}{j!}x^j \\
&=\sum_{j=0}^{\infty}\binom{k+j-1}{j}x^j.
\end{aligned}
$$

## 2.5 Example: Backpack

There are 8 types of items. Under the following restrictions, count the number of ways to take **exactly $N$ items**, modulo $10^9+7$, where $1\le N\le 10^{18}$.

- cola: at most 1;
- large chicken platter: at most 2;
- beer chicken: at most 3;
- chicken wings: an even number;
- chicken soup: an odd number;
- nuggets: a multiple of 4;
- drumsticks: at most 1;
- eggs: a multiple of 3.

Each item contributes one factor:

- cola:
  $$
  1+x=\frac{1-x^2}{1-x}
  $$
- large chicken platter:
  $$
  1+x+x^2=\frac{1-x^3}{1-x}
  $$
- beer chicken:
  $$
  1+x+x^2+x^3=\frac{1-x^4}{1-x}
  $$
- chicken wings:
  $$
  1+x^2+x^4+\cdots=\frac{1}{1-x^2}
  $$
- chicken soup:
  $$
  x+x^3+x^5+\cdots=\frac{x}{1-x^2}
  $$
- nuggets:
  $$
  1+x^4+x^8+\cdots=\frac{1}{1-x^4}
  $$
- drumsticks:
  $$
  1+x=\frac{1-x^2}{1-x}
  $$
- eggs:
  $$
  1+x^3+x^6+\cdots=\frac{1}{1-x^3}
  $$

Multiplying them all together gives

$$
G(x)=(1+x)^2(1+x+x^2)(1+x+x^2+x^3)\cdot\frac{x}{(1-x^2)^2(1-x^3)(1-x^4)}.
$$

So the answer is

$$
[x^N]G(x).
$$

A useful trick here is that for a finite polynomial such as $1+x+x^2$, we can regard it as sharing the same denominator as the infinite geometric series:

$$
(1+x+x^2)(1-x)=1-x^3,
$$

so

$$
1+x+x^2=\frac{1-x^3}{1-x}.
$$

## 2.6 Example: [CF 451E Devu and Flowers](https://codeforces.com/contest/451/problem/E)

There are $n$ types of flowers, with $f_1,f_2,\dots,f_n$ flowers of each type. Count the number of ways to choose exactly $s$ flowers.

$$
1\le n\le 20,\qquad 0\le f_i\le 10^{12},\qquad 0\le s\le 10^{14}.
$$

Start from the generating function, expand it, extract the coefficient, then enumerate subsets.

### Step 1: single-type generating function

For the $i$-th flower type,

$$
F_i(x)=1+x+x^2+\cdots+x^{f_i}
=\frac{1-x^{f_i+1}}{1-x}.
$$

### Step 2: factor the total generating function

$$
\begin{aligned}
F(x)
&=\prod_{i=1}^{n}F_i(x) \\
&=\prod_{i=1}^{n}\frac{1-x^{f_i+1}}{1-x} \\
&=\underbrace{\Bigl(\prod_{i=1}^{n}(1-x^{f_i+1})\Bigr)}_{A(x)}\cdot(1-x)^{-n}.
\end{aligned}
$$

where

$$
A(x)=\prod_{i=1}^{n}(1-x^{f_i+1}).
$$

### Step 3: expand $A(x)$

Each factor $(1-x^{f_i+1})$ contributes either:

- $1$, with exponent $0$ and sign $+$;
- $-x^{f_i+1}$, with exponent $f_i+1$ and sign $-$.

Therefore

$$
A(x)=\sum_{T\subseteq[n]}(-1)^{|T|}x^{\sum_{i\in T}(f_i+1)}.
$$

So $A(x)$ has at most $2^n$ terms.

### Step 4: extract $[x^s]F(x)$

$$
[x^s]F(x)
=\sum_{i=0}^{s}[x^i]A(x)\cdot [x^{s-i}]\frac{1}{(1-x)^n}.
$$

Since

$$
[x^{s-i}]\frac{1}{(1-x)^n}=\binom{s-i+n-1}{s-i},
$$

and $n$ is small, we can enumerate subsets directly to compute the contribution from $A(x)$.

### Step 5: complexity

- subset enumeration: $2^n$ subsets;
- combination query: $O(1)$ after preprocessing or $O(n)$ directly;
- total complexity:
  $$
  O(n\cdot 2^n).
  $$

This is completely feasible for $n\le 20$.

## 2.7 Example: [Luogu P6078 |CEOI2004| Sweets](https://www.luogu.com.cn/problem/P6078)

This is almost the same as the previous problem.

There are $n$ types of candies, with $m_1,m_2,\dots,m_n$ candies of each type. Count the number of ways to choose between $a$ and $b$ candies inclusive.

$$
1\le n\le 10,\qquad
0\le a\le b\le 10^7,\qquad
0\le m_i\le 10^6.
$$

- The generating function for type $i$ is
  $$
  F_i(x)=1+x+\cdots+x^{m_i}=\frac{1-x^{m_i+1}}{1-x}.
  $$

- The total generating function is
  $$
  \begin{aligned}
  F(x)
  &=\prod_{i=1}^{n}F_i(x) \\
  &=\prod_{i=1}^{n}\frac{1-x^{m_i+1}}{1-x} \\
  &=A(x)\cdot\frac{1}{(1-x)^n},
  \end{aligned}
  $$
  where
  $$
  A(x)=\prod_{i=1}^{n}(1-x^{m_i+1}).
  $$

- The number of valid selections is
  $$
  \sum_{s=a}^{b}[x^s]F(x)
  =\sum_{s=a}^{b}\sum_{i\ge 0}[x^i]A(x)\binom{s-i+n-1}{n-1}.
  $$

- Since $A(x)$ has at most $2^n$ nonzero coefficients, the direct complexity is
  $$
  O\bigl((b-a+1)\cdot n\cdot 2^n\bigr),
  $$
  which is too slow.

Rewrite it as

$$
\sum_{j=0}^{\deg A}[x^j]A(x)\cdot \sum_{s=a}^{b}\binom{s-j+n-1}{n-1}.
$$

Now the inner sum can be evaluated in $O(1)$ using the Hockey Stick identity, so the total complexity becomes

$$
O(n\cdot 2^n).
$$

---

# 3 From Recurrence to Generating Function to Closed Form

## 3.1 Typical flow

A typical workflow looks like this:

- recurrence:
  $$
  a_{n+2}+2a_{n+1}+a_n=n^2 2^n
  $$
- generating function:
  $$
  G(x)=\frac{2x^3(2x+1)}{(x+1)^2(2x-1)^3}
  $$
- then recover the closed form of $a_n$.

## 3.2 Example: Fibonacci numbers

The Fibonacci sequence satisfies

$$
a_0=0,\qquad a_1=1,\qquad a_n=a_{n-1}+a_{n-2}\quad (n\ge 2).
$$

We want its ordinary generating function.

### Step 1: obtain the generating function

$$
A(x)=\sum_{n=0}^{\infty}F_nx^n=\frac{x}{1-x-x^2}.
$$

### Step 2: derive the closed form

$$
\begin{aligned}
A(x)&=\frac{x}{1-x-x^2} \\
&=x\left(\frac{c}{1-ax}+\frac{d}{1-bx}\right).
\end{aligned}
$$

Matching coefficients gives

$$
a=\frac{1+\sqrt{5}}{2},\qquad
b=\frac{1-\sqrt{5}}{2},\qquad
c=\frac{1}{\sqrt{5}},\qquad
d=-\frac{1}{\sqrt{5}}.
$$

So the coefficient of $x^n$ is

$$
c\cdot a^{n-1}+d\cdot b^{n-1},
$$

which yields Binet's formula.

## 3.3 General $k$-th order linear recurrence

Suppose

$$
a_n=c_1a_{n-1}+c_2a_{n-2}+\cdots+c_ka_{n-k}.
$$

Let

$$
A(x)=\sum_{n\ge 0} a_nx^n.
$$

Then:

1. Split the series:
   $$
   A(x)=\sum_{n=0}^{k-1}a_nx^n+\sum_{n\ge k}a_nx^n.
   $$

2. Rewrite the tail:
   $$
   \sum_{n\ge k}a_nx^n
   =\sum_{i=1}^{k}c_i\sum_{n\ge k}a_{n-i}x^n
   =\sum_{i=1}^{k}c_ix^i\sum_{m\ge 0}a_mx^m
   -\sum_{i=1}^{k}c_ix^i\sum_{m=0}^{k-1-i}a_mx^m.
   $$

3. Rearrange:
   $$
   A(x)
   =\sum_{n=0}^{k-1}a_nx^n
   +\sum_{i=1}^{k}c_ix^iA(x)
   -\sum_{i=1}^{k}c_ix^i\sum_{m=0}^{k-1-i}a_mx^m.
   $$

4. Factor out $A(x)$:
   $$
   \bigl(1-c_1x-c_2x^2-\cdots-c_kx^k\bigr)A(x)
   =\sum_{n=0}^{k-1}\left(a_n-\sum_{i=1}^{n}c_ia_{n-i}\right)x^n
   \equiv B(x).
   $$

5. Final form:
   $$
   A(x)=\frac{B(x)}{1-c_1x-c_2x^2-\cdots-c_kx^k},
   $$
   where
   $$
   B(x)
   =a_0+(a_1-c_1a_0)x+\cdots+\left(a_{k-1}-\sum_{i=1}^{k-1}c_ia_{k-1-i}\right)x^{k-1}.
   $$

## 3.4 Example: Catalan numbers

The Catalan number

$$
C_n=\frac{1}{n+1}\binom{2n}{n}
$$

counts the number of valid parenthesizations of

$$
x_0x_1x_2\cdots x_n.
$$

For $n=3$, there are 5 ways:

$$
\begin{aligned}
&x_0\bigl(x_1(x_2x_3)\bigr), \\
&x_0\bigl((x_1x_2)x_3\bigr), \\
&\bigl(x_0x_1\bigr)\bigl(x_2x_3\bigr), \\
&\bigl(x_0(x_1x_2)\bigr)x_3, \\
&\bigl((x_0x_1)x_2\bigr)x_3.
\end{aligned}
$$

Let $c(n)$ be the number of ways to multiply $n+1$ numbers.
Looking at the last multiplication,

$$
\underbrace{(x_0\cdots x_i)}_{c(i)\text{ ways}}
\underbrace{(x_{i+1}\cdots x_n)}_{c(n-i-1)\text{ ways}},
$$

so

$$
c(n)=\sum_{i=0}^{n-1}c(i)c(n-i-1).
$$

Thus

$$
c_0=1,\qquad c_1=1,\qquad
c_n=c_0c_{n-1}+c_1c_{n-2}+\cdots+c_{n-1}c_0.
$$

Let

$$
c(x)=\sum_{n\ge 0}c_nx^n.
$$

Then

$$
\begin{aligned}
c(x)
&=1+x+\sum_{n\ge 2}\left(\sum_{i=0}^{n-1}c_ic_{n-1-i}\right)x^n \\
&=1+x+x(c(x)^2-1) \\
&=1+x\,c(x)^2.
\end{aligned}
$$

So

$$
x\,c(x)^2-c(x)+1=0.
$$

Hence

$$
c(x)=\frac{1\pm\sqrt{1-4x}}{2x}.
$$

Because $c(x)$ must be analytic at $x=0$ and have constant term $c_0=1$, we choose the minus branch:

$$
\boxed{c(x)=\frac{1-\sqrt{1-4x}}{2x}}.
$$

Now expand

$$
\sqrt{1-4x}
=\sum_{k=0}^{\infty}\binom{\tfrac12}{k}(-4x)^k
=1-2x-2\sum_{k=2}^{\infty}\frac{(2k-3)!}{(k-2)!(k-1)!}x^k.
$$

Substituting back,

$$
\begin{aligned}
c(x)
&=\frac{1-(1-2x+\cdots)}{2x} \\
&=\sum_{n=0}^{\infty}\underbrace{\frac{1}{n+1}\binom{2n}{n}}_{c_n}x^n.
\end{aligned}
$$

Therefore

$$
\boxed{c_n=\frac{1}{n+1}\binom{2n}{n}}.
$$

## 3.5 Why the minus branch?

Whenever solving an equation for a generating function gives

$$
F(x)=\frac{A(x)\pm\sqrt{B(x)}}{C(x)},
$$

we must test the branches at the origin.

The correct generating function must satisfy two properties:

1. it is analytic at $x=0$;
2. its constant term matches the known initial value.

Why does only one branch usually work?

- The "$+$" branch often leaves a nonzero constant term in the numerator, so the denominator's factor of $x$ cannot be canceled. The expansion then contains a term like $\frac{1}{x}$, so it diverges at the origin.
- The "$-$" branch often makes the numerator vanish to at least first order in $x$, which cancels the denominator and leaves an honest power series with the correct constant term.

So the practical procedure is:

1. solve for both branches;
2. expand each near $x=0$, or evaluate the limit at $x=0$;
3. keep the branch that stays finite and matches the initial value.
