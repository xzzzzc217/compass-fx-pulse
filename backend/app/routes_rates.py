from datetime import datetime
from flask import Blueprint, jsonify, request

from .db import get_cursor

bp = Blueprint("rates", __name__)


@bp.get("/api/exchange_rates")
def get_exchange_rates():
    currency_a = request.args.get("currencyA")
    currency_b = request.args.get("currencyB")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    if not (currency_a and currency_b and start_date and end_date):
        return jsonify({"error": "缺少必要的参数"}), 400
    try:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "日期格式错误"}), 400

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT currencytype1, currencytype2, time, rate
            FROM historicaldata
            WHERE currencytype1 = %s AND currencytype2 = %s
              AND time BETWEEN %s AND %s
            ORDER BY time
            """,
            (currency_a, currency_b, start_date, end_date),
        )
        rows = cur.fetchall()

    return jsonify([
        {
            "currencyA": row[0],
            "currencyB": row[1],
            "date": row[2].strftime("%Y-%m-%d"),
            "exchangeRate": float(row[3]),
        }
        for row in rows
    ])


@bp.get("/api/exchange_rate_prediction")
def exchange_rate_prediction():
    currency_a = request.args.get("currencyA")
    currency_b = request.args.get("currencyB")
    if not (currency_a and currency_b):
        return jsonify({"error": "缺少必要的参数"}), 400

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT time, rate FROM predictdata
            WHERE currencytype1 = %s AND currencytype2 = %s
            ORDER BY time
            """,
            (currency_a, currency_b),
        )
        rows = cur.fetchall()

    return jsonify({
        "dates": [r[0].strftime("%Y-%m-%d") if hasattr(r[0], "strftime") else r[0]
                  for r in rows],
        "rates": [float(r[1]) for r in rows],
    })
