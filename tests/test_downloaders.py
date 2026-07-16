from datetime import date

from crypto_analyser.downloaders import funding, ohlcv, open_interest


def test_binance_urls_are_built_from_domain_inputs():
    base = "https://data.example"
    assert ohlcv.build_url(base, "LUNAUSDT", "5m", "2022-05") == (
        "https://data.example/data/futures/um/monthly/klines/LUNAUSDT/5m/LUNAUSDT-5m-2022-05.zip"
    )
    assert funding.build_url(base, "LUNAUSDT", "2022-05") == (
        "https://data.example/data/futures/um/monthly/fundingRate/LUNAUSDT/LUNAUSDT-fundingRate-2022-05.zip"
    )
    assert open_interest.build_url(base, "LUNAUSDT", "2022-05-09") == (
        "https://data.example/data/futures/um/daily/metrics/LUNAUSDT/LUNAUSDT-metrics-2022-05-09.zip"
    )


def test_downloaders_reuse_existing_parquet(tmp_path):
    (tmp_path / "LUNAUSDT_2022-05.parquet").touch()

    assert ohlcv.download_ohlcv("LUNAUSDT", "2022-05", tmp_path)
    assert funding.download_funding("LUNAUSDT", "2022-05", tmp_path)
    assert open_interest.download_oi_range(
        "LUNAUSDT",
        date(2022, 5, 1),
        date(2022, 5, 11),
        tmp_path,
    )
