def get_percent_range_by_rarity(rarity: int):
    ranges = {
        0: (0, 100),
        1: (100, 110),
        2: (110, 120),
        3: (120, 130),
        4: (130, 140),
        5: (140, 150),
    }
    return ranges.get(rarity, (0, 100))


def get_rarity_by_percent_range(min_p: int, max_p: int):
    for rarity, (min_range, max_range) in {
        0: (0, 100),
        1: (100, 110),
        2: (110, 120),
        3: (120, 130),
        4: (130, 140),
        5: (140, 150),
    }.items():
        if min_range <= min_p < max_p <= max_range:
            return rarity
    return None
