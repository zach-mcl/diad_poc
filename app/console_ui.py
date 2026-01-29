from __future__ import annotations

from app.query_plan import QueryPlan, ColumnRef, Filter, Join
from app.db import find_join_candidates


def _pick(prompt: str, options: list[str]) -> int:
    while True:
        print(prompt)
        for i, opt in enumerate(options, 1):
            print(f"  {i}) {opt}")
        raw = input("> ").strip()
        if raw.isdigit():
            n = int(raw)
            if 1 <= n <= len(options):
                return n - 1
        print("Invalid choice.\n")


def _pick_multi(prompt: str, options: list[str]) -> list[int]:
    while True:
        print(prompt)
        for i, opt in enumerate(options, 1):
            print(f"  {i}) {opt}")
        raw = input("> ").strip()
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if not parts:
            print("Enter one or more numbers (e.g., 1,3).\n")
            continue

        idxs: list[int] = []
        ok = True
        for p in parts:
            if not p.isdigit():
                ok = False
                break
            n = int(p)
            if not (1 <= n <= len(options)):
                ok = False
                break
            idxs.append(n - 1)

        if ok and idxs:
            out = []
            seen = set()
            for i in idxs:
                if i not in seen:
                    out.append(i)
                    seen.add(i)
            return out

        print("Invalid selection.\n")


def run_console_builder(con, schema_map, categorical_index) -> QueryPlan:
    plan = QueryPlan()
    tables = sorted(schema_map.keys())

    def is_cat(t: str, c: str) -> bool:
        return (t, c) in categorical_index

    while True:
        print("\nAction:")
        print("  1) Add filter (chip)")
        print("  2) Add output column (chip)")
        print("  3) Show current plan")
        print("  4) Auto-suggest join(s) and select")
        print("  5) Run")
        print("  6) Quit")
        choice = input("> ").strip()

        if choice == "1":
            t = tables[_pick("\nPick table:", tables)]
            cols = sorted(schema_map[t].keys())
            c = cols[_pick("\nPick column:", cols)]

            if is_cat(t, c):
                vals = [v.strip() for v in categorical_index[(t, c)] if v and v.strip()]
                if len(vals) <= 1:
                    v = input(f"Enter value for {t}.{c}:\n> ").strip()
                    plan.filters.append(Filter(ColumnRef(t, c), "=", v))
                else:
                    idxs = _pick_multi(f"\nPick value(s) for {t}.{c} (comma-separated):", vals)
                    picked = [vals[i] for i in idxs]
                    if len(picked) == 1:
                        plan.filters.append(Filter(ColumnRef(t, c), "=", picked[0]))
                    else:
                        plan.filters.append(Filter(ColumnRef(t, c), "IN", picked))
                print(f"Added filter on {t}.{c}")

            else:
                ops = ["=", "!=", "LIKE", "ILIKE"]
                op = ops[_pick("\nPick operator:", ops)]
                v = input(f"Enter value for {t}.{c}:\n> ").strip()
                plan.filters.append(Filter(ColumnRef(t, c), op, v))
                print(f"Added filter on {t}.{c}")

        elif choice == "2":
            t = tables[_pick("\nPick table:", tables)]
            cols = sorted(schema_map[t].keys())
            c = cols[_pick("\nPick column:", cols)]
            plan.selected.append(ColumnRef(t, c))
            print(f"Added output: {t}.{c}")

        elif choice == "3":
            print("\nCurrent plan:")
            if plan.selected:
                print("  Output:")
                for c in plan.selected:
                    print(f"   - {c.table}.{c.column}")
            else:
                print("  Output: (none; defaults to base table *)")

            if plan.filters:
                print("  Filters:")
                for f in plan.filters:
                    print(f"   - {f.col.table}.{f.col.column} {f.op} {f.value}")
            else:
                print("  Filters: (none)")

            if plan.joins:
                print("  Joins:")
                for j in plan.joins:
                    print(f"   - {j.left_table}.{j.left_col} ↔ {j.right_table}.{j.right_col}")
            else:
                print("  Joins: (none)")

        elif choice == "4":
            ref = sorted(plan.referenced_tables())
            if len(ref) < 2:
                print("\nOnly one table referenced; no joins needed.")
                continue

            base = ref[0]
            for other in ref[1:]:
                candidates = find_join_candidates(con, schema_map, base, other, sample_limit=200, min_overlap=0.05)
                if not candidates:
                    print(f"\nNo join candidates found between {base} and {other}.")
                    continue
                opts = [f"{base}.{lc} ↔ {other}.{rc} (overlap≈{score:.2f})" for lc, rc, score in candidates]
                idx = _pick(f"\nPick join for {base} ↔ {other}:", opts)
                lc, rc, _ = candidates[idx]
                plan.joins.append(Join(base, lc, other, rc))
                print(f"Added join: {base}.{lc} ↔ {other}.{rc}")

        elif choice == "5":
            return plan

        elif choice == "6":
            raise SystemExit(0)

        else:
            print("Invalid choice.")
