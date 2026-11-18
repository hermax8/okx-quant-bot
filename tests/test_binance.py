from okxbot.data.binance_public import parse_funding_csv


def test_parse_with_header():
    raw = b"calc_time,funding_interval_hours,last_funding_rate\n1577836800000,8,0.00010000\n1577865600000,8,-0.00002500\n"
    df = parse_funding_csv(raw)
    assert list(df["funding_time"]) == [1577836800000, 1577865600000]
    assert abs(df["funding_rate"].iloc[1] + 0.000025) < 1e-12
    assert list(df["interval_h"]) == [8, 8]


def test_parse_without_header():
    raw = b"1577836800000,8,0.0001\n1577865600000,8,0.0002\n"
    df = parse_funding_csv(raw)
    assert len(df) == 2 and df["funding_rate"].iloc[1] == 0.0002
