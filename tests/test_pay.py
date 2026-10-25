from job_agent.pay import from_ashby, from_greenhouse, from_lever, from_text


def test_text_ranges() -> None:
    assert from_text("The base salary range is $250,000 - $340,000 per year.").high == 340_000
    pay = from_text("Pay: $216.7K/yr - $322K/yr")
    assert pay.low == 216_700 and pay.high == 322_000
    assert from_text("USD $230,000 – $345,000").high == 345_000
    assert from_text("Salary 230000 - 345000 USD").high == 345_000


def test_text_picks_highest_range() -> None:
    text = "Zone A: $200,000 - $280,000. Zone B (SF Bay Area): $240,000 - $330,000."
    assert from_text(text).high == 330_000


def test_text_rejects_non_pay() -> None:
    assert from_text("CA$215K – CA$295K") is None
    assert from_text("$60 - $80 per hour") is None
    assert from_text("We grew from 2020 - 2024") is None
    assert from_text("serving 10,000 - 50,000 customers") is None


def test_implausible_amounts_are_dropped() -> None:
    grant = {
        "compensationType": "Salary",
        "interval": "1 YEAR",
        "currencyCode": "USD",
        "minValue": 5_000_000,
        "maxValue": 5_000_000,
    }
    assert from_ashby({"compensationTiers": [{"components": [grant]}]}) is None


def test_structured() -> None:
    gh = [{"min_cents": 30000000, "max_cents": 40000000, "currency_type": "USD"}]
    assert from_greenhouse(gh).high == 400_000
    salary = {
        "compensationType": "Salary",
        "interval": "1 YEAR",
        "currencyCode": "USD",
        "minValue": 200000,
        "maxValue": 330000,
    }
    equity = {**salary, "compensationType": "EquityCashValue", "minValue": None, "maxValue": None}
    assert from_ashby({"compensationTiers": [{"components": [equity, salary]}]}).high == 330_000
    cad = {**salary, "currencyCode": "CAD"}
    assert from_ashby({"compensationTiers": [{"components": [cad]}]}) is None
    yearly = {"min": 250000, "max": 310000, "currency": "USD", "interval": "per-year-salary"}
    assert from_lever(yearly).high == 310_000
    assert (
        from_lever({"min": 50, "max": 70, "currency": "USD", "interval": "per-hour-wage"}) is None
    )
