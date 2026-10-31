from collections import Counter
from decimal import ROUND_HALF_UP, Decimal


def rank_rows(rows: list[dict], criteria: list[object]) -> list[dict]:
    """Competition ranking; criteria averages remain unrounded for tie breaking."""
    ordered = sorted(criteria, key=lambda c: (-c.weight, c.order))

    def key(row: dict) -> tuple:
        averages = {str(c["criterion_id"]): Decimal(c["avg"]) for c in row["criteria"]}
        return (
            -Decimal(row["total"]),
            *(-averages[str(c.id)] for c in ordered),
            row["submitted_at"],
        )

    rows = sorted(rows, key=lambda r: (key(r), r["team"]["id"]))
    counts = Counter(key(row) for row in rows)
    previous = None
    rank = 0
    result = []
    for index, row in enumerate(rows, 1):
        current = key(row)
        if current != previous:
            rank = index
        result.append(
            {k: v for k, v in row.items() if k != "submitted_at"}
            | {
                "rank": rank,
                "tied": counts[current] > 1,
            }
        )
        previous = current
    return result


def calculate(
    teams: list[object],
    submissions: dict,
    assignments: list[object],
    scores: list[object],
    criteria: list[object],
) -> dict:
    rows = []
    results = {}
    for team in teams:
        active = [a for a in assignments if a.team_id == team.id and a.status == "submitted"]
        if not active or team.id not in submissions:
            continue
        values = {
            a.id: {s.criterion_id: s for s in scores if s.assignment_id == a.id} for a in active
        }
        if any(set(values[a.id]) != {c.id for c in criteria} for a in active):
            continue
        averages = {
            c.id: sum((values[a.id][c.id].score for a in active), Decimal(0)) / len(active)
            for c in criteria
        }
        total = sum((averages[c.id] / c.max_score * c.weight for c in criteria), Decimal(0))
        row = {
            "team": {
                "id": str(team.id),
                "name": team.name,
                "track_id": str(team.track_id) if team.track_id else None,
            },
            "total": str(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "criteria": [{"criterion_id": str(c.id), "avg": str(averages[c.id])} for c in criteria],
            "submitted_at": submissions[team.id].submitted_at.isoformat(),
        }
        rows.append(row)
        results[str(team.id)] = {
            "criteria": [{"name": c.name, "avg": str(averages[c.id])} for c in criteria],
            "comments": [
                comment
                for a in active
                for comment in [a.general_comment, *(s.comment for s in values[a.id].values())]
                if comment
            ],
        }
    boards = {"all": rank_rows(rows, criteria)}
    for track in {r["team"]["track_id"] for r in rows} - {None}:
        boards[track] = rank_rows([r for r in rows if r["team"]["track_id"] == track], criteria)
    for row in boards["all"]:
        results[row["team"]["id"]].update(rank=row["rank"], total=row["total"])
    return {"boards": boards, "results": results}
