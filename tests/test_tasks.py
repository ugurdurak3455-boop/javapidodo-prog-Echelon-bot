"""Tests for background task helpers."""

from tasks import limit_jobs_for_cycle


def test_limit_jobs_for_cycle_keeps_small_batch():
    jobs = [{"id": 1}, {"id": 2}]

    selected, skipped = limit_jobs_for_cycle(jobs, max_jobs=10)

    assert selected == jobs
    assert skipped == 0


def test_limit_jobs_for_cycle_truncates_large_batch():
    jobs = [{"id": i} for i in range(5)]

    selected, skipped = limit_jobs_for_cycle(jobs, max_jobs=3)

    assert selected == jobs[:3]
    assert skipped == 2
