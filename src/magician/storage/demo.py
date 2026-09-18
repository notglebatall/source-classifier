from __future__ import annotations

import argparse
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb

from magician.config import DATABASE_PATH


REGIONS = [
    (1, "Москва", "Центральный"),
    (2, "Санкт-Петербург", "Северо-Западный"),
    (3, "Республика Татарстан", "Приволжский"),
    (4, "Свердловская область", "Уральский"),
    (5, "Новосибирская область", "Сибирский"),
    (6, "Краснодарский край", "Южный"),
]

BANKS = [
    (1, "Столичный банк", 1, "частный", "крупный", date(2010, 1, 1), None),
    (2, "Федеральный кредит", 1, "государственный", "крупный", date(2006, 1, 1), None),
    (3, "Северный банк", 2, "частный", "средний", date(2012, 3, 1), None),
    (4, "Волга Финанс", 3, "частный", "средний", date(2015, 5, 1), None),
    (5, "Урал Капитал", 4, "частный", "средний", date(2011, 8, 1), None),
    (6, "Сибирский расчётный банк", 5, "региональный", "малый", date(2018, 2, 1), None),
    (7, "Южный коммерческий банк", 6, "региональный", "малый", date(2016, 6, 1), None),
    (8, "Новые платежи", 1, "частный", "малый", date(2020, 9, 1), None),
    (9, "Балтийский резерв", 2, "частный", "малый", date(2017, 4, 1), None),
    (10, "Казанский деловой банк", 3, "региональный", "малый", date(2013, 11, 1), None),
    (11, "Евразия банк", 4, "частный", "средний", date(2014, 7, 1), None),
    (12, "Точка роста", 5, "частный", "малый", date(2024, 7, 1), None),
]


def month_starts(start: date, count: int) -> list[date]:
    months = []
    year, month = start.year, start.month
    for _ in range(count):
        months.append(date(year, month, 1))
        month += 1
        if month == 13:
            year += 1
            month = 1
    return months


def amount(value: int | float) -> Decimal:
    return Decimal(str(round(value, 2)))


def create_schema(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE TABLE dim_region (
            region_id INTEGER PRIMARY KEY,
            region_name VARCHAR NOT NULL UNIQUE,
            federal_district VARCHAR NOT NULL
        );

        CREATE TABLE dim_bank (
            bank_id INTEGER PRIMARY KEY,
            bank_name VARCHAR NOT NULL UNIQUE,
            region_id INTEGER NOT NULL REFERENCES dim_region(region_id),
            ownership_type VARCHAR NOT NULL,
            size_segment VARCHAR NOT NULL,
            active_from DATE NOT NULL,
            active_to DATE
        );

        CREATE TABLE fact_balance_monthly (
            report_month DATE NOT NULL,
            bank_id INTEGER NOT NULL REFERENCES dim_bank(bank_id),
            assets_mln_rub DECIMAL(18, 2) NOT NULL,
            liabilities_mln_rub DECIMAL(18, 2) NOT NULL,
            capital_mln_rub DECIMAL(18, 2) NOT NULL,
            loans_mln_rub DECIMAL(18, 2) NOT NULL,
            deposits_mln_rub DECIMAL(18, 2) NOT NULL,
            PRIMARY KEY (report_month, bank_id)
        );

        CREATE TABLE fact_income_monthly (
            period_month DATE NOT NULL,
            bank_id INTEGER NOT NULL REFERENCES dim_bank(bank_id),
            interest_income_mln_rub DECIMAL(18, 2) NOT NULL,
            fee_income_mln_rub DECIMAL(18, 2) NOT NULL,
            operating_expense_mln_rub DECIMAL(18, 2) NOT NULL,
            net_profit_mln_rub DECIMAL(18, 2) NOT NULL,
            PRIMARY KEY (period_month, bank_id)
        );

        CREATE TABLE fact_customers_monthly (
            report_month DATE NOT NULL,
            bank_id INTEGER NOT NULL REFERENCES dim_bank(bank_id),
            customer_segment VARCHAR NOT NULL,
            active_customers INTEGER NOT NULL,
            accounts INTEGER NOT NULL,
            deposits_mln_rub DECIMAL(18, 2) NOT NULL,
            PRIMARY KEY (report_month, bank_id, customer_segment)
        );
        """
    )


def seed_data(connection: duckdb.DuckDBPyConnection) -> None:
    connection.executemany("INSERT INTO dim_region VALUES (?, ?, ?)", REGIONS)
    connection.executemany("INSERT INTO dim_bank VALUES (?, ?, ?, ?, ?, ?, ?)", BANKS)

    balances = []
    incomes = []
    customers = []
    segments = (("розничный", 1.0), ("малый и средний бизнес", 0.12), ("корпоративный", 0.025))

    for month_index, report_month in enumerate(month_starts(date(2024, 1, 1), 24)):
        for bank_id, _, _, _, size_segment, active_from, _ in BANKS:
            if report_month < active_from.replace(day=1):
                continue

            size_factor = {"крупный": 9.0, "средний": 3.5, "малый": 1.0}[size_segment]
            assets = (7_500 + bank_id * 730) * size_factor * (1 + month_index * 0.012)
            capital = assets * (0.105 + (bank_id % 4) * 0.006)
            liabilities = assets - capital
            loans = assets * (0.52 + (bank_id % 3) * 0.025)
            deposits = liabilities * (0.68 + (bank_id % 2) * 0.035)
            balances.append(
                (
                    report_month,
                    bank_id,
                    amount(assets),
                    amount(liabilities),
                    amount(capital),
                    amount(loans),
                    amount(deposits),
                )
            )

            interest_income = loans * (0.0105 + (bank_id % 3) * 0.0007)
            fee_income = assets * (0.0014 + (bank_id % 2) * 0.0002)
            operating_expense = assets * (0.0046 + (bank_id % 4) * 0.00015)
            net_profit = interest_income + fee_income - operating_expense
            if not (bank_id == 12 and report_month == date(2025, 12, 1)):
                incomes.append(
                    (
                        report_month,
                        bank_id,
                        amount(interest_income),
                        amount(fee_income),
                        amount(operating_expense),
                        amount(net_profit),
                    )
                )

            base_customers = int((18_000 + bank_id * 1_900) * size_factor)
            for segment, segment_factor in segments:
                active_customers = int(base_customers * segment_factor * (1 + month_index * 0.009))
                accounts = int(active_customers * (1.18 + (bank_id % 3) * 0.05))
                segment_deposits = deposits * {
                    "розничный": 0.52,
                    "малый и средний бизнес": 0.23,
                    "корпоративный": 0.25,
                }[segment]
                customers.append(
                    (
                        report_month,
                        bank_id,
                        segment,
                        active_customers,
                        accounts,
                        amount(segment_deposits),
                    )
                )

    connection.executemany("INSERT INTO fact_balance_monthly VALUES (?, ?, ?, ?, ?, ?, ?)", balances)
    connection.executemany("INSERT INTO fact_income_monthly VALUES (?, ?, ?, ?, ?, ?)", incomes)
    connection.executemany("INSERT INTO fact_customers_monthly VALUES (?, ?, ?, ?, ?, ?)", customers)


def initialize_database(path: str | Path | None = None, *, overwrite: bool = False) -> Path:
    target = Path(path) if path else DATABASE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        raise FileExistsError(f"База уже существует: {target}. Используйте --force для пересоздания.")

    temporary = target.with_suffix(f"{target.suffix}.tmp")
    if temporary.exists():
        temporary.unlink()

    connection = duckdb.connect(str(temporary))
    try:
        create_schema(connection)
        seed_data(connection)
        connection.execute("CHECKPOINT")
    finally:
        connection.close()

    os.replace(temporary, target)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Создать тестовую базу SQL-агента")
    parser.add_argument("--path", type=Path, default=DATABASE_PATH)
    parser.add_argument("--force", action="store_true", help="Пересоздать существующую базу")
    args = parser.parse_args()
    created_path = initialize_database(args.path, overwrite=args.force)
    print(created_path)


if __name__ == "__main__":
    main()
