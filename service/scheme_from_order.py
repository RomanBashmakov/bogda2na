#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scheme_from_order.py — заказ конструктора → производственная схема.

Внутренний инструмент мастера: берёт service/orders/NNN/order.json и
выпускает печатную A4-схему с кружками-бисеринами и номерами коробочек
(picher/render.py): основной HTML + одноцветные файлы на каждый цвет.
Клиенту эта схема не показывается никогда.

Запуск из корня проекта:
    python3 service/scheme_from_order.py 0001      # один заказ
    python3 service/scheme_from_order.py --all      # все без схемы
Выход: service/orders/NNN/схема/*.html
"""

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

SRV = Path(__file__).resolve().parent
ORDERS = SRV / "orders"
RENDER_PY = SRV.parent / "picher" / "render.py"


def _render_mod():
    """Модуль picher/render.py (печатные схемы, без Pillow)."""
    spec = importlib.util.spec_from_file_location("picher_render",
                                                  RENDER_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_scheme(order_dir: Path, mod) -> None:
    order = json.loads((order_dir / "order.json").read_text(
        encoding="utf-8"))
    num = order_dir.name
    colors = [{"name": f"цвет {i + 1}", "hex": h}
              for i, h in enumerate(order["colors"])]
    data = {"version": 1, "name": f"заказ_{num}",
            "cols": order["cols"], "rows": order["rows"],
            "colors": colors, "cells": order["cells"]}
    out = order_dir / "схема"
    files = mod.write_outputs(
        data, name=f"заказ_{num}",
        title=f"Заказ №{num} · {order['format']} · {order['level_label']}"
              f" · {order['name']}",
        pitch_mm=4.5, circle_d_mm=3.0, out_dir=out)
    print(f"заказ {num}: {files['main']} + "
          f"{len(files['singles'])} одноцветных")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Заказ конструктора → печатная схема мастера")
    ap.add_argument("order", nargs="?", help="номер заказа, напр. 0001")
    ap.add_argument("--all", action="store_true",
                    help="обработать все заказы")
    args = ap.parse_args()
    if not ORDERS.is_dir() or not any(ORDERS.iterdir()):
        print("Заказов нет (service/orders/ пуст).")
        return 0
    mod = _render_mod()
    if args.all:
        for d in sorted(ORDERS.iterdir()):
            if d.is_dir():
                make_scheme(d, mod)
        return 0
    if not args.order or not re.fullmatch(r"\d{1,4}", args.order):
        print("Укажите номер заказа (например 0001) или --all.")
        print("Есть заказы:",
              ", ".join(d.name for d in sorted(ORDERS.iterdir())
                        if d.is_dir()) or "—")
        return 1
    d = ORDERS / args.order.zfill(4)
    if not d.is_dir():
        print(f"Заказа {d.name} нет.")
        return 1
    make_scheme(d, mod)
    return 0


if __name__ == "__main__":
    sys.exit(main())
