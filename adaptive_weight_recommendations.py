from typing import Any, Dict, List

from factor_analysis import get_factor_effectiveness_report

RECOMMENDATION_VERSION = "2.18.0"

CURRENT_MODEL_WEIGHTS = {
    "last10": 0.15, "win_place": 0.08, "track_record": 0.08,
    "distance_record": 0.09, "track_distance": 0.09, "track_condition": 0.12,
    "trainer": 0.10, "jockey": 0.08, "trainer_jockey": 0.12,
    "barrier": 0.04, "weight": 0.02, "market": 0.03,
}



def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _suggest_weight_change(factor: Dict[str, Any], dataset_confidence: str) -> Dict[str, Any]:
    key = factor.get("factor"); label = factor.get("label"); current_weight = CURRENT_MODEL_WEIGHTS.get(str(key), 0.0)
    combined = _to_float(factor.get("combined_predictive_score")); winner_gap = _to_float(factor.get("winner_gap")); place_gap = _to_float(factor.get("place_gap")); sample_confidence = factor.get("confidence")
    if dataset_confidence in ["Low", "Early"] or sample_confidence == "Low":
        recommended_weight = current_weight; direction = "Hold"; priority = "Low"; reason = "Dataset is not mature enough for a reliable weight change."
    elif combined >= 0.18 and winner_gap > 5 and place_gap > 3:
        recommended_weight = current_weight + 0.02; direction = "Increase"; priority = "High"; reason = f"{label} has a strong positive relationship to both winners and placegetters."
    elif combined >= 0.10 and (winner_gap > 3 or place_gap > 2):
        recommended_weight = current_weight + 0.01; direction = "Slight Increase"; priority = "Medium"; reason = f"{label} shows useful positive separation in the completed runner dataset."
    elif combined <= -0.08 and winner_gap < 0 and place_gap < 0:
        recommended_weight = max(0.0, current_weight - 0.02); direction = "Reduce"; priority = "Medium"; reason = f"{label} is not separating successful runners and may be over-weighted."
    elif abs(combined) < 0.05:
        recommended_weight = max(0.0, current_weight - 0.01); direction = "Monitor / Possible Reduction"; priority = "Low"; reason = f"{label} has a very weak observed relationship to outcomes."
    else:
        recommended_weight = current_weight; direction = "Hold"; priority = "Medium"; reason = f"{label} has an observable but not decisive outcome relationship."
    return {"factor": key, "label": label, "current_weight": current_weight, "recommended_weight": round(recommended_weight, 2), "change": round(recommended_weight - current_weight, 2), "direction": direction, "priority": priority, "confidence": sample_confidence, "signal_strength": factor.get("signal_strength"), "combined_predictive_score": combined, "winner_gap": winner_gap, "place_gap": place_gap, "reason": reason}


def get_weight_recommendations() -> Dict[str, Any]:
    try:
        effectiveness = get_factor_effectiveness_report()
        if not effectiveness.get("success"):
            return effectiveness
        dataset = effectiveness.get("dataset") or {}; dataset_confidence = dataset.get("confidence") or "Low"
        recommendations: List[Dict[str, Any]] = [_suggest_weight_change(factor, dataset_confidence) for factor in effectiveness.get("factors") or []]
        increase = [item for item in recommendations if item.get("change", 0) > 0]
        reduce = [item for item in recommendations if item.get("change", 0) < 0]
        hold = [item for item in recommendations if item.get("change", 0) == 0]
        net_change = round(sum(_to_float(item.get("change")) for item in recommendations), 2)
        return {"success": True, "provider": "RRT Predictor", "recommendation_version": RECOMMENDATION_VERSION, "report": "weight_recommendations", "analysis_only": True, "prediction_model_changed": False, "dataset": dataset, "current_model_weights": CURRENT_MODEL_WEIGHTS, "recommendations": recommendations, "summary": {"dataset_confidence": dataset_confidence, "increase_candidates": len(increase), "reduction_candidates": len(reduce), "hold_candidates": len(hold), "net_recommended_weight_change": net_change, "top_increase_candidates": sorted(increase, key=lambda item: item.get("change") or 0, reverse=True)[:5], "top_reduction_candidates": sorted(reduce, key=lambda item: item.get("change") or 0)[:5]}, "safety_note": "These are recommendation-only values. No production model weights have been changed."}
    except Exception as error:
        return {"success": False, "provider": "RRT Predictor", "recommendation_version": RECOMMENDATION_VERSION, "report": "weight_recommendations", "error": str(error)}
