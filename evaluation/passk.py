from typing import Iterable


def estimate_pass_at_k(n: int, c: int, k: int) -> float:
    """
    Unbiased pass@k estimator from code-generation evaluation literature.

    n: number of samples for one task
    c: number of correct samples among n
    k: requested top-k
    """
    if n <= 0 or k <= 0:
        return 0.0
    if c <= 0:
        return 0.0
    if k > n:
        k = n
    if n - c < k:
        return 1.0

    failure_prob = 1.0
    for i in range(k):
        failure_prob *= (n - c - i) / (n - i)
    return 1.0 - failure_prob


def aggregate_pass_at_k(correct_counts: Iterable[int], n: int, k: int) -> float:
    counts = list(correct_counts)
    if not counts:
        return 0.0
    return sum(estimate_pass_at_k(n=n, c=c, k=k) for c in counts) / len(counts)
