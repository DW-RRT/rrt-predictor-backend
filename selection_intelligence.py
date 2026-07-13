from typing import Any, Dict, List, Optional
import json
from datetime import datetime

from database import fetch_all, fetch_one, execute_sql
from learning_dataset import get_learning_dataset_audit, load_learning_rows


SELECTION_INTELLIGENCE_VERSION = "2.18.0"
MODEL_VERSION = "2.18.0"


FACTOR_COLUMNS = [
    ("last10_score", "Last 10 Form"),
    ("win_place_score", "Win / Place Record"),
    ("track_record_score", "Track Record"),
    ("distance_record_score", "Distance Record"),
    ("track_distance_record_score", "Track / Distance Record"),
    ("track_condition_score", "Track Condition"),
    ("trainer_score", "Trainer"),
    ("jockey_score", "Jockey"),
    ("trainer_jockey_score", "Trainer / Jockey"),
    ("barrier_score", "Barrier"),
    ("weight_score", "Weight Carried"),
    ("market_score", "Market"),
]


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _json_dumps(value: Any) -> str:
    return json.dumps(value, default=str)


def _load_completed_rows(
    min_meeting_date: Optional[str] = None,
    max_meeting_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    return load_learning_rows(
        min_meeting_date=min_meeting_date,
        max_meeting_date=max_meeting_date,
        model_version=None,
    )


def _group_by_race(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(f"{row.get('meeting_id')}|{row.get('race_number')}", []).append(row)
    return grouped


def _rank_race(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked = sorted(
        rows,
        key=lambda item: (
            _to_float(item.get("final_score")),
            _to_float(item.get("confidence")),
            -_to_float(item.get("market_price"), 9999),
        ),
        reverse=True,
    )
    return [{**row, "rrt_rank": index + 1} for index, row in enumerate(ranked)]


def _factor_gap_summary(winner: Dict[str, Any], top4: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not winner or not top4:
        return []

    avg_top4: Dict[str, float] = {}
    for column, label in FACTOR_COLUMNS:
        avg_top4[column] = round(sum(_to_float(item.get(column), 50.0) for item in top4) / max(len(top4), 1), 2)

    gaps = []
    for column, label in FACTOR_COLUMNS:
        winner_score = round(_to_float(winner.get(column), 50.0), 2)
        top4_average = avg_top4.get(column, 50.0)
        gap = round(winner_score - top4_average, 2)
        gaps.append({
            "factor": column.replace("_score", ""),
            "label": label,
            "winner_score": winner_score,
            "top4_average": top4_average,
            "gap": gap,
            "interpretation": "Winner stronger than selected group" if gap >= 5 else "Winner weaker than selected group" if gap <= -5 else "Similar to selected group",
        })

    return sorted(gaps, key=lambda item: abs(_to_float(item.get("gap"))), reverse=True)


def _miss_reason(winner: Dict[str, Any], top4: List[Dict[str, Any]]) -> List[str]:
    reasons: List[str] = []
    rank = _to_int(winner.get("rrt_rank"))
    market_rank = _to_int(winner.get("market_rank"), 99)
    price = _to_float(winner.get("market_price"))

    if rank == 5:
        reasons.append("Winner was a boundary miss ranked 5th.")
    elif 6 <= rank <= 8:
        reasons.append("Winner was close but outside the Top 4.")
    elif rank > 8:
        reasons.append("Winner was materially under-ranked by the current selection logic.")

    if market_rank >= 6 and price >= 7:
        reasons.append("Winner had roughie/value characteristics and may need better value-index handling.")
    elif market_rank <= 3:
        reasons.append("Winner was market-supported but still missed by RRT ranking.")

    gaps = _factor_gap_summary(winner, top4)
    positive = [gap for gap in gaps if _to_float(gap.get("gap")) >= 8]
    negative = [gap for gap in gaps if _to_float(gap.get("gap")) <= -8]

    if positive:
        labels = ", ".join(item.get("label") for item in positive[:3])
        reasons.append(f"Winner was stronger than selected runners on: {labels}.")
    if negative:
        labels = ", ".join(item.get("label") for item in negative[:3])
        reasons.append(f"Winner was weaker than selected runners on: {labels}.")

    if not reasons:
        reasons.append("No single dominant miss driver identified.")

    return reasons


def _analyse_race(race_key: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    ranked = _rank_race(rows)
    top4 = ranked[:4]
    winner = next((item for item in ranked if _to_int(item.get("actual_position")) == 1), None)

    if not winner:
        return {}

    winner_rank = _to_int(winner.get("rrt_rank"))
    top4_hit = winner_rank <= 4
    near_miss = 5 <= winner_rank <= 8
    boundary_miss = winner_rank == 5
    false_positives = [item for item in top4 if _to_int(item.get("actual_position"), 999) not in [1, 2, 3]]
    roughie_like_winner = _to_float(winner.get("market_price")) >= 7 and _to_int(winner.get("market_rank"), 99) >= 5
    top4_score_floor = min([_to_float(item.get("final_score")) for item in top4], default=0.0)

    return {
        "race_key": race_key,
        "meeting_id": winner.get("meeting_id"),
        "track": winner.get("track"),
        "meeting_date": winner.get("meeting_date"),
        "race_number": winner.get("race_number"),
        "runner_count": len(ranked),
        "winner": {
            "runner": winner.get("runner_name"),
            "tab_number": winner.get("tab_number"),
            "rrt_rank": winner_rank,
            "final_score": winner.get("final_score"),
            "confidence": winner.get("confidence"),
            "market_price": winner.get("market_price"),
            "market_rank": winner.get("market_rank"),
            "actual_price": winner.get("actual_price"),
        },
        "top4_hit": top4_hit,
        "near_miss": near_miss,
        "boundary_miss": boundary_miss,
        "roughie_like_winner": roughie_like_winner,
        "score_gap_to_top4_floor": round(_to_float(winner.get("final_score")) - top4_score_floor, 2),
        "top4": [
            {
                "runner": item.get("runner_name"),
                "tab_number": item.get("tab_number"),
                "rrt_rank": item.get("rrt_rank"),
                "final_score": item.get("final_score"),
                "market_price": item.get("market_price"),
                "market_rank": item.get("market_rank"),
                "actual_position": item.get("actual_position"),
            }
            for item in top4
        ],
        "false_positive_count": len(false_positives),
        "false_positives": [
            {
                "runner": item.get("runner_name"),
                "rrt_rank": item.get("rrt_rank"),
                "final_score": item.get("final_score"),
                "market_price": item.get("market_price"),
                "actual_position": item.get("actual_position"),
            }
            for item in false_positives
        ],
        "factor_gaps": _factor_gap_summary(winner, top4),
        "miss_reasons": [] if top4_hit else _miss_reason(winner, top4),
    }


def _factor_gap_rollup(missed_races: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    collector: Dict[str, Dict[str, Any]] = {}
    for race in missed_races:
        for gap in race.get("factor_gaps") or []:
            key = gap.get("factor")
            if not key:
                continue
            collector.setdefault(key, {
                "factor": key,
                "label": gap.get("label"),
                "count": 0,
                "total_gap": 0.0,
                "positive_gap_count": 0,
                "negative_gap_count": 0,
            })
            value = _to_float(gap.get("gap"))
            collector[key]["count"] += 1
            collector[key]["total_gap"] += value
            if value >= 5:
                collector[key]["positive_gap_count"] += 1
            elif value <= -5:
                collector[key]["negative_gap_count"] += 1

    rows = []
    for item in collector.values():
        count = max(_to_int(item.get("count")), 1)
        avg_gap = round(_to_float(item.get("total_gap")) / count, 2)
        rows.append({
            "factor": item.get("factor"),
            "label": item.get("label"),
            "missed_race_count": item.get("count"),
            "average_winner_gap_vs_top4": avg_gap,
            "positive_gap_count": item.get("positive_gap_count"),
            "negative_gap_count": item.get("negative_gap_count"),
            "direction": "Potentially underweighted" if avg_gap >= 3 else "Potentially overweighted" if avg_gap <= -3 else "Neutral",
        })
    return sorted(rows, key=lambda item: abs(_to_float(item.get("average_winner_gap_vs_top4"))), reverse=True)


def _build_selection_recommendations(
    race_count: int,
    near_miss_count: int,
    boundary_miss_count: int,
    roughie_like_winner_count: int,
    false_positive_total: int,
    factor_gap_rollup: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    recommendations: List[Dict[str, Any]] = []
    if race_count <= 0:
        return recommendations

    near_rate = near_miss_count / race_count
    boundary_rate = boundary_miss_count / race_count
    roughie_like_rate = roughie_like_winner_count / race_count
    false_positive_rate = false_positive_total / race_count

    if near_rate >= 0.12:
        recommendations.append({
            "priority": "High",
            "area": "Top 4 Boundary",
            "recommendation": "Test a Top 4 boundary promotion rule for runners ranked 5th to 8th where factor evidence is strong.",
            "evidence": f"{near_miss_count} races had winners ranked 5th to 8th.",
            "next_step": "v2.17 should simulate controlled promotion rules before production use.",
        })

    if boundary_rate >= 0.04:
        recommendations.append({
            "priority": "High",
            "area": "Rank 5 Misses",
            "recommendation": "Analyse rank-5 winners as the first candidate for decision-logic optimisation.",
            "evidence": f"{boundary_miss_count} winners were ranked exactly 5th.",
            "next_step": "Test whether rank-5 winners can be promoted using market/value/factor confirmation.",
        })

    if roughie_like_rate >= 0.08:
        recommendations.append({
            "priority": "High",
            "area": "Value / Roughie Logic",
            "recommendation": "Introduce a value index to detect higher-priced winners that the model rates competitively.",
            "evidence": f"{roughie_like_winner_count} winners had roughie-like market characteristics.",
            "next_step": "Simulate value-index based roughie and each-way promotion rules.",
        })

    if false_positive_rate >= 1.5:
        recommendations.append({
            "priority": "Medium",
            "area": "False Positives",
            "recommendation": "Review Top 4 runners that consistently fail to place despite high RRT scores.",
            "evidence": f"Average false positives per race: {round(false_positive_rate, 2)}.",
            "next_step": "Identify whether false positives are driven by weak market, weight, barrier, or track signals.",
        })

    for factor in factor_gap_rollup[:3]:
        avg_gap = _to_float(factor.get("average_winner_gap_vs_top4"))
        if avg_gap >= 3:
            recommendations.append({
                "priority": "Medium",
                "area": factor.get("label"),
                "recommendation": f"Review whether {factor.get('label')} should influence selection promotion more strongly.",
                "evidence": f"Missed winners averaged {avg_gap} points stronger than Top 4 selections on this factor.",
                "next_step": "Use v2.17 optimisation to test a rule-based promotion rather than direct production weight change.",
            })
        elif avg_gap <= -3:
            recommendations.append({
                "priority": "Medium",
                "area": factor.get("label"),
                "recommendation": f"Review whether {factor.get('label')} is suppressing winners or over-rewarding false positives.",
                "evidence": f"Missed winners averaged {avg_gap} points weaker than Top 4 selections on this factor.",
                "next_step": "Use v2.17 optimisation to test controlled reduction or gating rules.",
            })

    if not recommendations:
        recommendations.append({
            "priority": "Medium",
            "area": "Selection Stability",
            "recommendation": "No dominant selection miss pattern was found. Continue collecting data and focus on value-index testing.",
            "evidence": "Misses are distributed across several factors rather than one clear driver.",
            "next_step": "Proceed to v2.17 with conservative optimisation trials.",
        })

    return recommendations


def run_selection_intelligence_analysis(
    min_meeting_date: Optional[str] = None,
    max_meeting_date: Optional[str] = None,
    save_result: bool = True,
) -> Dict[str, Any]:
    try:
        rows = _load_completed_rows(min_meeting_date=min_meeting_date, max_meeting_date=max_meeting_date)
        grouped = _group_by_race(rows)
        race_analyses = []
        for race_key, race_rows in grouped.items():
            analysed = _analyse_race(race_key, race_rows)
            if analysed:
                race_analyses.append(analysed)

        race_count = len(race_analyses)
        hit_count = sum(1 for item in race_analyses if item.get("top4_hit"))
        miss_count = race_count - hit_count
        near_miss_count = sum(1 for item in race_analyses if item.get("near_miss"))
        boundary_miss_count = sum(1 for item in race_analyses if item.get("boundary_miss"))
        roughie_like_winner_count = sum(1 for item in race_analyses if item.get("roughie_like_winner"))
        false_positive_total = sum(_to_int(item.get("false_positive_count")) for item in race_analyses)
        missed_races = [item for item in race_analyses if not item.get("top4_hit")]
        top_misses = sorted(
            missed_races,
            key=lambda item: (
                _to_int((item.get("winner") or {}).get("rrt_rank"), 999),
                abs(_to_float(item.get("score_gap_to_top4_floor"))),
            ),
        )[:25]
        factor_gap_rollup = _factor_gap_rollup(missed_races)
        recommendations = _build_selection_recommendations(
            race_count=race_count,
            near_miss_count=near_miss_count,
            boundary_miss_count=boundary_miss_count,
            roughie_like_winner_count=roughie_like_winner_count,
            false_positive_total=false_positive_total,
            factor_gap_rollup=factor_gap_rollup,
        )

        response = {
            "success": True,
            "provider": "RRT Predictor",
            "selection_intelligence_version": SELECTION_INTELLIGENCE_VERSION,
            "report": "selection_intelligence",
            "analysis_only": True,
            "prediction_model_changed": False,
            "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "dataset": {
                "runner_rows": len(rows),
                "race_count": race_count,
                "min_meeting_date": min_meeting_date,
                "max_meeting_date": max_meeting_date,
                "audit": get_learning_dataset_audit(),
                "capture_requirement": "full_field_pre_race_only",
            },
            "summary": {
                "top4_hit_count": hit_count,
                "top4_miss_count": miss_count,
                "top4_hit_rate": round((hit_count / race_count) * 100, 2) if race_count else 0.0,
                "top4_miss_rate": round((miss_count / race_count) * 100, 2) if race_count else 0.0,
                "near_miss_count": near_miss_count,
                "boundary_miss_count": boundary_miss_count,
                "near_miss_rate": round((near_miss_count / race_count) * 100, 2) if race_count else 0.0,
                "boundary_miss_rate": round((boundary_miss_count / race_count) * 100, 2) if race_count else 0.0,
                "roughie_like_winner_count": roughie_like_winner_count,
                "roughie_like_winner_rate": round((roughie_like_winner_count / race_count) * 100, 2) if race_count else 0.0,
                "false_positive_total": false_positive_total,
                "avg_false_positives_per_race": round(false_positive_total / race_count, 2) if race_count else 0.0,
            },
            "factor_gap_rollup": factor_gap_rollup,
            "recommendations": recommendations,
            "top_misses": top_misses,
            "safety_note": "Selection intelligence is analysis-only. No production scoring weights or live prediction behaviour have been changed.",
        }
        if save_result:
            response["postgres_history"] = save_selection_analysis(response)
        return response
    except Exception as error:
        return {
            "success": False,
            "provider": "RRT Predictor",
            "selection_intelligence_version": SELECTION_INTELLIGENCE_VERSION,
            "report": "selection_intelligence",
            "error": str(error),
        }


def save_selection_analysis(analysis: Dict[str, Any]) -> Dict[str, Any]:
    try:
        execute_sql(
            """
            INSERT INTO rrt_selection_analysis (
                analysis_version, model_version, generated_at, dataset_runner_count, dataset_race_count,
                top4_hit_rate, near_miss_rate, boundary_miss_rate, roughie_like_winner_rate, analysis_json
            )
            VALUES (%s, %s, NOW(), %s, %s, %s, %s, %s, %s, %s::jsonb);
            """,
            (
                analysis.get("selection_intelligence_version"),
                MODEL_VERSION,
                (analysis.get("dataset") or {}).get("runner_rows"),
                (analysis.get("dataset") or {}).get("race_count"),
                (analysis.get("summary") or {}).get("top4_hit_rate"),
                (analysis.get("summary") or {}).get("near_miss_rate"),
                (analysis.get("summary") or {}).get("boundary_miss_rate"),
                (analysis.get("summary") or {}).get("roughie_like_winner_rate"),
                _json_dumps(analysis),
            ),
        )
        return {"success": True, "provider": "PostgreSQL", "message": "Selection intelligence analysis saved."}
    except Exception as error:
        return {"success": False, "provider": "PostgreSQL", "message": "Failed to save selection intelligence analysis.", "error": str(error)}


def get_selection_analysis_history(limit: int = 10) -> Dict[str, Any]:
    try:
        rows = fetch_all(
            """
            SELECT id, analysis_version, model_version, generated_at, dataset_runner_count, dataset_race_count,
                   top4_hit_rate, near_miss_rate, boundary_miss_rate, roughie_like_winner_rate
            FROM rrt_selection_analysis
            ORDER BY generated_at DESC
            LIMIT %s;
            """,
            (limit,),
        )
        return {
            "success": True,
            "provider": "PostgreSQL",
            "selection_intelligence_version": SELECTION_INTELLIGENCE_VERSION,
            "report": "selection_analysis_history",
            "limit": limit,
            "analysis_count": len(rows),
            "analyses": rows,
        }
    except Exception as error:
        return {"success": False, "provider": "PostgreSQL", "selection_intelligence_version": SELECTION_INTELLIGENCE_VERSION, "report": "selection_analysis_history", "error": str(error)}


def get_latest_selection_analysis() -> Dict[str, Any]:
    try:
        row = fetch_one("SELECT analysis_json FROM rrt_selection_analysis WHERE analysis_version = '2.18.0' ORDER BY generated_at DESC LIMIT 1;")
        if not row:
            return run_selection_intelligence_analysis(save_result=True)
        analysis = row.get("analysis_json") or {}
        if isinstance(analysis, str):
            analysis = json.loads(analysis)
        return {
            "success": True,
            "provider": "PostgreSQL",
            "selection_intelligence_version": SELECTION_INTELLIGENCE_VERSION,
            "report": "latest_selection_analysis",
            "analysis": analysis,
        }
    except Exception as error:
        return {"success": False, "provider": "PostgreSQL", "selection_intelligence_version": SELECTION_INTELLIGENCE_VERSION, "report": "latest_selection_analysis", "error": str(error)}


def get_top_misses(limit: int = 25) -> Dict[str, Any]:
    analysis = run_selection_intelligence_analysis(save_result=False)
    if not analysis.get("success"):
        return analysis
    misses = analysis.get("top_misses") or []
    return {
        "success": True,
        "provider": "RRT Predictor",
        "selection_intelligence_version": SELECTION_INTELLIGENCE_VERSION,
        "report": "top_misses",
        "limit": limit,
        "miss_count": len(misses[:limit]),
        "top_misses": misses[:limit],
        "summary": analysis.get("summary"),
    }


def get_factor_impact_report() -> Dict[str, Any]:
    analysis = run_selection_intelligence_analysis(save_result=False)
    if not analysis.get("success"):
        return analysis
    return {
        "success": True,
        "provider": "RRT Predictor",
        "selection_intelligence_version": SELECTION_INTELLIGENCE_VERSION,
        "report": "factor_impact",
        "factor_gap_rollup": analysis.get("factor_gap_rollup"),
        "recommendations": analysis.get("recommendations"),
        "summary": analysis.get("summary"),
    }


def get_category_analysis() -> Dict[str, Any]:
    analysis = run_selection_intelligence_analysis(save_result=False)
    if not analysis.get("success"):
        return analysis
    summary = analysis.get("summary") or {}
    return {
        "success": True,
        "provider": "RRT Predictor",
        "selection_intelligence_version": SELECTION_INTELLIGENCE_VERSION,
        "report": "category_analysis",
        "analysis_only": True,
        "categories": {
            "top4_boundary": {
                "near_miss_count": summary.get("near_miss_count"),
                "near_miss_rate": summary.get("near_miss_rate"),
                "boundary_miss_count": summary.get("boundary_miss_count"),
                "boundary_miss_rate": summary.get("boundary_miss_rate"),
            },
            "roughie_value": {
                "roughie_like_winner_count": summary.get("roughie_like_winner_count"),
                "roughie_like_winner_rate": summary.get("roughie_like_winner_rate"),
            },
            "false_positives": {
                "false_positive_total": summary.get("false_positive_total"),
                "avg_false_positives_per_race": summary.get("avg_false_positives_per_race"),
            },
        },
        "recommendations": analysis.get("recommendations"),
        "safety_note": "Category analysis is observational only.",
    }
