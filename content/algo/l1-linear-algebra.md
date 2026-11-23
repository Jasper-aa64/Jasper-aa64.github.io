---
title: "L1: Linear Algebra"
date: 2026-11-23
slug: "l1-linear-algebra"
description: "A mental model of linear algebra: a linear space is a set closed under addition and scaling, a basis is a set of vectors that cannot be thinned further, and finding one is Gaussian elimination; the same 0/1 vectors can have different ranks over the reals and over GF(2) because the arithmetic differs; a matrix is a linear map, and everything about solving equations comes from its image and kernel (rank–nullity); the determinant tells whether the map flattens space. Ends with how the tools of C0 section 4 and the L2 XOR basis fit the model."
weight: 15
math: true
toc: true
---
> The essence of linear algebra: sets closed under addition and scalar multiplication, and the maps that preserve both operations.

The first kind is a linear space and the second kind is a matrix. Matrix exponentiation, Gaussian elimination, XOR bases and determinants in contests all ask different questions about these two objects. This post sets up the model: spaces and bases (sections 1 and 2), how to find a basis (section 3), what changes with a different field (section 4), matrices and solving equations (sections 5 and 6), determinants (section 7), and how the concrete tools fit (section 8).

## 1. Linear Spaces: Adding and Scaling Never Leave the Set

A set whose elements (called vectors) stay inside the set when added together or multiplied by any coefficient is a **linear space**. It always contains the zero vector, since any vector times 0 gives it.

Where the coefficients come from is the **field**: a set of arithmetic rules in which addition, subtraction, multiplication and division by non-zero elements all work. Contests use three:

| Field | Coefficients | What a vector is | Typical problems |
| --- | --- | --- | --- |
| Reals $\mathbb{R}$ | any real number | real coordinates | expectation systems with cycles, geometry |
| Integers mod a prime $\mathbb{F}_p$ | $0$ to $p-1$, division becomes multiplying by an inverse | coordinates mod $p$ | counting, solving systems mod $p$, determinants |
| GF(2) | only 0 and 1 | a 0/1 string, i.e. the binary digits of an integer | xor, light switches |

The definitions and statements in this post only use the four operations, so they hold word for word in all three fields.

Examples and non-examples:

- In $\mathbb{R}^2$, the line through the origin $\{(t, 2t)\}$ is a linear space: sums and multiples of its points stay on the line.
- A line missing the origin is not, because multiplying by 0 lands on the origin; the first quadrant is not either, because multiplying by $-1$ leaves it.
- Over GF(2), $\{0, 3, 5, 6\}$ is a linear space, since the xor of any two of its elements is still in it; $\{0, 1, 2\}$ is not, since $1 \oplus 2 = 3$.

## 2. Basis, Dimension, Rank: the Fewest Vectors That Describe the Whole Space

The set of all linear combinations $k_1 v_1 + k_2 v_2 + \cdots + k_n v_n$ of some vectors is their **span**, and it is automatically a linear space. If one of the vectors is a combination of the others it is redundant, and removing it leaves the span unchanged. Remove until nothing more can go: what remains is **linearly independent** (only the all-zero combination gives the zero vector), it is a **basis** of the space, and its size is the **dimension** of the space. The dimension of the span of some vectors is their **rank**.

Two properties of a basis are used again and again:

- **Unique representation**: every element of the space has exactly one set of coefficients on the basis. If it had two, subtracting them would give a combination of the basis with coefficients not all 0 that equals the zero vector, contradicting independence.
- **The dimension fixes the number of elements**: an element of an $r$-dimensional space is a choice of $r$ coefficients. Over the reals there are infinitely many, modulo $p$ there are $p^r$, and over GF(2) there are $2^r$.

## 3. Finding a Basis: Gaussian Elimination Turns Redundant Vectors into 0

Finding a basis means turning "remove the redundant vectors" into an algorithm, and the algorithm is Gaussian elimination.

1. Put the $n$ vectors in the $n$ rows of a matrix.
2. Starting from the first column, pick a row that is non-zero in this column as the pivot row, swap it up, and use it to clear this column in the rows below: subtract $k$ times the pivot row from row $j$, where $k$ is row $j$'s entry in this column divided by the pivot.
3. After all columns are done, the non-zero rows form a basis, and their number is the rank.

Why it works:

- Elimination only replaces a row by a combination of it with other rows, which keeps the span.
- A redundant vector is a combination of other rows, so it is cleared to an all-zero row.
- Each remaining non-zero row has a pivot column that is 0 in the rows below it, so none of them is a combination of the others, and they are linearly independent.

Example (reals): $u = (1, 1, 0)$, $v = (0, 1, 1)$, $w = (1, 2, 1)$.

- Column 1: $u$ is the pivot row; $w$ minus $u$ gives $(0, 1, 1)$.
- Column 2: $v$ is the pivot row; $w$ minus $v$ gives $(0, 0, 0)$.

$w$ is cleared to 0 because $w = u + v$. The basis is $\{u, v\}$ and the rank is 2.

## 4. A Different Field: the Same 0/1 Vectors Can Change Rank

> The essence of changing the field: the arithmetic changes, not the numbers stored in the vectors.

Over the reals $1 + 1 = 2$; over GF(2) $1 + 1 = 0$. Vectors with only 0 and 1 in them, taken over the reals, produce 2 when added and $-1$ or $\frac12$ when scaled, leaving the 0/1 range. GF(2) is a different set of rules: only 0 and 1, and addition adds bit by bit mod 2, i.e. xor. The same $(1, 0, 1)$ computes differently on the two sides.

### 4.1 Example: Rank 3 or Rank 2

Three vectors $u = (1, 1, 0)$, $v = (0, 1, 1)$, $w = (1, 0, 1)$:

| | Reals $\mathbb{R}$ | GF(2) |
| --- | --- | --- |
| $u + v$ | $(1, 2, 1)$ | $(1, 0, 1) = w$ |
| $u + v + w$ | $(2, 2, 2)$, not the zero vector | $(0, 0, 0)$ |
| Independent? | yes, rank 3 | no, $w = u + v$, rank 2 |
| Span | all of $\mathbb{R}^3$, infinitely many points | 4 points: $000, 110, 011, 101$ |

As integers they are 6, 3, 5: $6 \oplus 3 = 5$, so inserting them into an XOR basis clears 5 to 0, while over the reals no coefficients combine them into the zero vector.

### 4.2 Only the Arithmetic Table Changes; Concepts and Procedures Carry Over

| | Reals | GF(2) |
| --- | --- | --- |
| Coefficients | any real number | only 0 and 1 |
| Addition | $1 + 1 = 2$ | $1 + 1 = 0$, i.e. xor |
| Subtraction | ordinary subtraction | the same as addition, $-1 = 1$ |
| One elimination step | row $j$ minus $k$ times the pivot row | row $j$ xor the pivot row |
| Linear independence | only the all-zero combination gives the zero vector | no non-empty subset XORs to 0 |
| Size of an $r$-dimensional space | infinite | $2^r$ |

The definitions of linear space, basis, rank, span and kernel only use "addition" and "scaling", so they still hold with the new table. Gaussian elimination carries over too: over GF(2) the only non-zero coefficient is 1, subtracting once equals adding once, and "subtract $k$ times" becomes "xor". So do not think of GF(2) as "real vectors that happen to contain only 0 and 1": it is a new field, and in it 0/1 strings are vectors and xor is vector addition.

### 4.3 Over GF(2) a Basis Vector Is an Integer

A 0/1 string fits exactly in the binary digits of an integer, and Gaussian elimination for a basis becomes the XOR basis:

| | Ordinary linear algebra | XOR basis |
| --- | --- | --- |
| A vector | coordinates, e.g. $(1, 0, 1)$ | an integer, e.g. $5 = 101_2$ |
| Adding vectors | add entry by entry | `x ^ y` |
| Basis | the non-zero rows after elimination | the non-zero numbers in `b[0..59]` |
| Pivot | the first non-zero column of each non-zero row | the highest bit of `b[i]` is exactly bit $i$ |

An XOR basis eliminates in a different order from section 3: instead of taking the whole matrix and clearing column by column, it **eliminates each number as it arrives**. To insert $x$, scan from the high bit down; if bit $i$ is 1 and `b[i]` is occupied, `x ^= b[i]` clears that bit, which is one row operation; if `b[i]` is empty, store $x$ there as a new basis vector; if $x$ is cleared all the way to 0, it is the XOR of existing basis vectors and is redundant.

Example: insert $3 = 011_2$, $5 = 101_2$, $6 = 110_2$ in order.

- Insert 3: the highest bit is bit 1, `b[1]` is empty, store it, `b[1] = 011`.
- Insert 5: the highest bit is bit 2, `b[2]` is empty, store it, `b[2] = 101`.
- Insert 6: bit 2 is 1, XOR with `b[2]` gives $110 \oplus 101 = 011$; bit 1 is 1, XOR with `b[1]` gives $011 \oplus 011 = 000$. It is cleared to 0, so $6 = 3 \oplus 5$ is redundant.

The basis is $\{3, 5\}$ with rank 2, and it reaches $2^2 = 4$ values $\{0, 3, 5, 6\}$: the linear space from section 1. Code, counting and maxima are in [L2 XOR Basis](/algo/l2-xor-basis/).

## 5. A Matrix Is a Linear Map

An $m \times n$ matrix $A$ sends an $n$-dimensional vector $x$ to an $m$-dimensional vector $Ax$ and preserves addition and scaling: $A(x + y) = Ax + Ay$ and $A(kx) = k \cdot Ax$. A map that preserves both operations is a **linear map**. Conversely every linear map can be written as a matrix: column $j$ holds the image of the $j$-th unit vector. So a matrix and a linear map are the same thing.

This gives two readings:

- **Matrix multiplication is composition of maps**: $(AB)x = A(Bx)$, first $B$ and then $A$. Composition is associative by nature, which is exactly what fast matrix exponentiation relies on.
- **$Ax$ is a linear combination of the columns of $A$**, with the entries of $x$ as coefficients: $Ax = x_1 \cdot (\text{column } 1) + \cdots + x_n \cdot (\text{column } n)$. So everything $A$ can reach is the span of its columns.

## 6. Image and Kernel: Everything About Solving Equations

A linear map $A$ comes with two spaces:

- The **image** (also called the column space): every reachable $Ax$. Its dimension is the rank $r$ of $A$.
- The **kernel**: every $x$ that $A$ sends to the zero vector, i.e. all solutions of the homogeneous system $Ax = 0$.

The **rank–nullity theorem** ties them together: the kernel has dimension $n - r$, where $n$ is the number of unknowns. One way to see it: $x$ has $n$ degrees of freedom, $r$ of them decide where in the image the result lands, and the other $n - r$ can change freely without changing the result; those $n - r$ directions are the kernel.

Everything about solving $Ax = b$ follows:

- **Is there a solution**: exactly when $b$ is in the image. A row reading "$0 = $ non-zero" after elimination means $b$ is not in the image.
- **What the solutions look like**: take any one solution $x_0$; all solutions are $x_0$ plus any vector of the kernel. The difference of two solutions satisfies $A(x_1 - x_0) = b - b = 0$, so it lies in the kernel.
- **How many solutions**: as many as the kernel has elements. The kernel has dimension $n - r$, so modulo $p$ there are $p^{n-r}$ solutions; $n - r$ is the number of free variables after elimination.

The XOR-basis fact that "every reachable value is reached by exactly $2^{n-r}$ subsets" is the same statement: write a choice of subset as $x \in \{0, 1\}^n$; "choice to xor sum" is a linear map over GF(2), its image is the set of reachable values with $2^r$ elements, and the choices giving one value form a shifted copy of the kernel with $2^{n-r}$ elements.

<a href="/images/algo/kernel-image.en.svg" target="_blank" rel="noopener"><img src="/images/algo/kernel-image.en.svg" alt="Image and kernel of a linear map A. Left, the input space: the blue line through the origin is the kernel, all solutions of Ax = 0, of dimension n − r; the dashed orange line parallel to it through x₀ is the set of all solutions of Ax = b. A sends the whole blue line to 0 and the whole orange line to b. Right, the output space: the blue plane is the image, every result A can reach, of dimension r; b′ outside the image has no solution. The dimensions of kernel and image add up to n, and the number of solutions equals the size of the kernel." loading="lazy" decoding="async"></a>

## 7. Determinant: Does the Map Flatten Space

For a square matrix $A$, over the reals $\det A$ is the factor by which the map scales volume, with the sign telling whether orientation flips. $\det A = 0$ means $A$ squashes the $n$-dimensional space into fewer dimensions, so some non-zero vector must go to the zero vector. The following all say the same thing:

- $\det A \ne 0$;
- the rank is $n$;
- the kernel contains only the zero vector;
- for every $b$, $Ax = b$ has exactly one solution;
- $A$ is invertible.

Counting problems use another form of the determinant: $\det A = \sum_{\sigma} \operatorname{sgn}(\sigma) \prod_{i} A_{i, \sigma(i)}$, a signed sum over all permutations $\sigma$. The matrix-tree theorem and the LGV lemma both build a matrix whose signed sum counts exactly the configurations wanted.

## 8. Each Tool in the Model

The tools of [C0 section 4](/algo/c0-contest-math-overview/), and the question each asks in the model:

| Tool | Question |
| --- | --- |
| Matrix power | the result of applying the same linear map $n$ times: $v_n = M^{n-1} v_1$ |
| (min, +) matrices | leave linear spaces, keep only associativity and distributivity, and fast exponentiation still works |
| BM | the sequence produced by repeatedly applying a fixed linear map satisfies a linear recurrence of order at most the dimension |
| Gaussian elimination | find the rank, decide whether $b$ is in the image, count the dimension of the kernel (the free variables) |
| XOR basis | build a basis of the span over GF(2), one insertion at a time |
| Determinant | whether the map is invertible, and counting through a signed sum over permutations |

The concepts behind each section of [L2 XOR Basis](/algo/l2-xor-basis/):

| Ordinary linear algebra | In an XOR basis | Section of L2 |
| --- | --- | --- |
| Linear space | all values reachable by XOR-ing any subset | 1.1, 1.2 |
| Basis, rank | the non-zero numbers in `b`, $r \le 60$ of them | 2.1 |
| Finding a basis by Gaussian elimination | insertion: eliminate each number as it arrives | 2.1 to 2.3 |
| Unique representation, $2^r$ elements in $r$ dimensions | $2^r$ distinct XOR values | 3.1 |
| Kernel of dimension $n - r$ | each value reached by $2^{n-r}$ subsets | 3.2 |
| Reduced row echelon form | normalisation, $k$-th smallest | 4.2, 4.3 |
