from meridian.core.ratelimit import RateBudget


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_budget_blocks_then_resets_with_the_window():
    clock = Clock()
    rb = RateBudget(quota=100, window_s=300, budget_share=0.5, clock=clock)
    assert rb.limit == 50
    assert all(rb.try_spend(5) for _ in range(10))
    assert not rb.try_spend(5)
    assert rb.try_spend(0)  # cancels always allowed
    clock.t = 301
    assert rb.try_spend(5)


def test_429_blocks_until_reset():
    clock = Clock()
    rb = RateBudget(clock=clock)
    rb.on_429(2000)
    assert not rb.ok and not rb.try_spend(5)
    assert rb.try_spend(0)
    clock.t = 2.1
    assert rb.ok and rb.try_spend(5)
