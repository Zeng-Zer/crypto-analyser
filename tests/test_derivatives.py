import pandas as pd

from crypto_analyser.features.derivatives import extract_features

HOUR = 3_600_000


def test_extract_features_anchors_at_episode_onset():
    episodes = [{"onset_ts": 9 * HOUR}]
    funding = pd.DataFrame(
        {
            "calc_time": [0, 8 * HOUR],
            "funding_rate": [0.001, 0.003],
        }
    )
    oi = pd.DataFrame(
        {
            "create_time_ms": [5 * HOUR, 9 * HOUR],
            "sum_open_interest": [100.0, 120.0],
        }
    )

    assert extract_features(episodes, funding, oi) == [
        {
            "onset_ts": 9 * HOUR,
            "funding_rate_current": 0.003,
            "funding_rate_avg_4h": 0.0015,
            "oi_current": 120.0,
            "oi_change_4h": 0.2,
        }
    ]
