from konsilier.core.rating import CategoryStats, LawyerStats, score

BASE = {"consumer": 0.6}


def lawyer(cases, won, partial=0, on_time=None, total=None, reviews=(0, 0.0)):
    total = total if total is not None else cases * 3
    return LawyerStats([CategoryStats("consumer", cases, won, partial, 1000.0 * cases, 700.0 * cases)],
                       total, on_time if on_time is not None else total, reviews[0], reviews[1])


def test_small_perfect_sample_does_not_beat_large_strong_record():
    newbie = score(lawyer(3, 3), BASE)
    veteran = score(lawyer(220, 180), BASE)
    assert veteran.total > newbie.total
    assert newbie.confidence == "low" and veteran.confidence == "high"


def test_average_lawyer_scores_at_baseline():
    s = score(lawyer(100, 60), BASE)
    assert abs(s.vs_baseline) < 0.5


def test_missed_milestones_lower_the_score():
    punctual = score(lawyer(80, 55, on_time=240, total=240), BASE)
    late = score(lawyer(80, 55, on_time=150, total=240), BASE)
    assert punctual.total > late.total


def test_easy_categories_do_not_inflate_score():
    # same 70% success, but in a category where the platform average is 70% vs 40%
    easy = score(LawyerStats([CategoryStats("easy", 100, 70, 0)], 0, 0), {"easy": 0.7})
    hard = score(LawyerStats([CategoryStats("hard", 100, 70, 0)], 0, 0), {"hard": 0.4})
    assert hard.total > easy.total


def test_lawyers_endpoint_ranks_demo_profiles(ctx):
    r = ctx.client.get("/v1/lawyers?country=KZ").json()
    assert r["demo"] is True and "вымышлены" in r["disclaimer"]
    totals = [p["score"]["total"] for p in r["lawyers"]]
    assert totals == sorted(totals, reverse=True) and len(totals) == 5
    assert all("(демо)" in p["name"] for p in r["lawyers"])
