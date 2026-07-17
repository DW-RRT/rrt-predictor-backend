from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import json, os, uuid

from database import execute_sql, fetch_all, fetch_one
from factor_analysis import get_factor_effectiveness_report
from adaptive_weight_recommendations import get_weight_recommendations
from simulator_engine import run_weight_simulation
from selection_intelligence import run_selection_intelligence_analysis

LEARNING_VERSION = "2.19.0"
MODEL_VERSION = "2.19.0"
AUTO_PROMOTION_ENABLED = os.getenv("RRT_AUTO_WEIGHT_PROMOTION_ENABLED", "true").lower() == "true"
MIN_NATIVE_RACES = int(os.getenv("RRT_PROMOTION_MIN_NATIVE_RACES", "150"))
MIN_COMPLETED_RUNNERS = int(os.getenv("RRT_PROMOTION_MIN_COMPLETED_RUNNERS", "1200"))
MIN_OVERALL_IMPROVEMENT = float(os.getenv("RRT_PROMOTION_MIN_OVERALL_IMPROVEMENT", "1.0"))
MIN_TOP_WIN_IMPROVEMENT = float(os.getenv("RRT_PROMOTION_MIN_TOP_WIN_IMPROVEMENT", "0.0"))
MAX_EACH_WAY_DEGRADATION = float(os.getenv("RRT_PROMOTION_MAX_EACH_WAY_DEGRADATION", "1.5"))
MIN_STABILITY_INDEX = float(os.getenv("RRT_PROMOTION_MIN_STABILITY_INDEX", "70"))
REQUIRED_READY_CYCLES = int(os.getenv("RRT_PROMOTION_REQUIRED_READY_CYCLES", "2"))


def _f(v: Any, d: float=0.0)->float:
    try: return d if v is None else float(v)
    except Exception: return d

def _i(v: Any, d: int=0)->int:
    try: return d if v is None else int(float(v))
    except Exception: return d

def _active_weight_row()->Dict[str,Any]:
    return fetch_one("SELECT model_version,weights_json,activated_at FROM rrt_model_weight_sets WHERE status='Active' ORDER BY activated_at DESC NULLS LAST,created_at DESC LIMIT 1;") or {}

def _normalise(weights: Dict[str,Any])->Dict[str,float]:
    clean={k:max(0.0,_f(v)) for k,v in weights.items()}
    total=sum(clean.values())
    if total<=0: raise ValueError("Proposed weights total must be positive.")
    scaled={k:round(v*100.0/total,2) for k,v in clean.items()}
    delta=round(100.0-sum(scaled.values()),2)
    if scaled: scaled[max(scaled,key=scaled.get)]=round(scaled[max(scaled,key=scaled.get)]+delta,2)
    return scaled

def _candidate(weight_report: Dict[str,Any])->Dict[str,float]:
    current=dict(weight_report.get("current_model_weights") or {})
    for r in weight_report.get("recommendations") or []:
        current[str(r.get("factor"))]=_f(r.get("recommended_weight"),_f(current.get(str(r.get("factor")))))
    return _normalise(current)

def _dataset()->Dict[str,Any]:
    row=fetch_one("""SELECT COUNT(*) AS runner_rows, COUNT(*) FILTER (WHERE actual_position IS NOT NULL) AS completed_runner_rows,
        COUNT(DISTINCT meeting_id) AS meeting_count,
        COUNT(DISTINCT (meeting_id::text||'|'||COALESCE(race_number::text,''))) FILTER (WHERE actual_position IS NOT NULL AND model_version IN ('2.18.3','2.18.4','2.19.0')) AS native_completed_races,
        MIN(meeting_date) AS first_meeting_date, MAX(meeting_date) AS latest_meeting_date FROM rrt_runner_factor_snapshots;""") or {}
    return {"source":"historical_factor_analysis_plus_native_capture","runner_rows":_i(row.get("runner_rows")),"completed_runner_rows":_i(row.get("completed_runner_rows")),"meeting_count":_i(row.get("meeting_count")),"native_completed_races":_i(row.get("native_completed_races")),"first_meeting_date":row.get("first_meeting_date"),"latest_meeting_date":row.get("latest_meeting_date"),"historical_learning_retained":True,"native_full_field_capture_active":True}

def _recent_ready_cycles()->int:
    row=fetch_one("""SELECT COUNT(*) AS count FROM (SELECT cycle_json FROM rrt_learning_cycles ORDER BY created_at DESC LIMIT %s) x
        WHERE COALESCE(cycle_json->'promotion_gate'->>'decision','')='Ready for Production';""",(REQUIRED_READY_CYCLES-1,)) or {}
    return _i(row.get("count"))

def _gate(dataset:Dict[str,Any], simulation:Dict[str,Any])->Dict[str,Any]:
    imp=simulation.get("improvement") or {}
    sens=simulation.get("sensitivity") or {}
    checks={
      "minimum_native_races": dataset.get("native_completed_races",0)>=MIN_NATIVE_RACES,
      "minimum_completed_runners": dataset.get("completed_runner_rows",0)>=MIN_COMPLETED_RUNNERS,
      "overall_improvement": _f(imp.get("overall_accuracy"))>=MIN_OVERALL_IMPROVEMENT,
      "top_win_not_degraded": _f(imp.get("top_win_strike_rate"))>=MIN_TOP_WIN_IMPROVEMENT,
      "each_way_within_tolerance": _f(imp.get("each_way_strike_rate"))>=-MAX_EACH_WAY_DEGRADATION,
      "stability": _f(sens.get("prediction_stability_index"),100)>=MIN_STABILITY_INDEX,
    }
    ready=all(checks.values())
    consecutive=_recent_ready_cycles()+1 if ready else 0
    return {"decision":"Ready for Production" if ready else "Monitor","checks":checks,"thresholds":{"min_native_races":MIN_NATIVE_RACES,"min_completed_runners":MIN_COMPLETED_RUNNERS,"min_overall_improvement":MIN_OVERALL_IMPROVEMENT,"min_top_win_improvement":MIN_TOP_WIN_IMPROVEMENT,"max_each_way_degradation":MAX_EACH_WAY_DEGRADATION,"min_stability_index":MIN_STABILITY_INDEX,"required_ready_cycles":REQUIRED_READY_CYCLES},"consecutive_ready_cycles":consecutive,"promotion_authorised":ready and consecutive>=REQUIRED_READY_CYCLES and AUTO_PROMOTION_ENABLED}

def _promote(cycle_id:str, current:Dict[str,Any], proposed:Dict[str,float], gate:Dict[str,Any])->Dict[str,Any]:
    promotion_id=f"promote-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    new_id=f"2.19.0-auto-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    execute_sql("UPDATE rrt_model_weight_sets SET status='Rollback' WHERE status='Active';")
    execute_sql("""INSERT INTO rrt_model_weight_sets(model_version,status,weights_json,source,notes,activated_at,promoted_by_cycle_id,promotion_evidence_json,automatic_promotion)
       VALUES(%s,'Active',%s::jsonb,'Adaptive Learning','Automatically promoted after all v2.19.0 safety gates passed.',NOW(),%s,%s::jsonb,TRUE);""",
       (new_id,json.dumps(proposed),cycle_id,json.dumps(gate,default=str)))
    execute_sql("""INSERT INTO rrt_weight_promotion_audit(promotion_id,cycle_id,from_weight_set,to_weight_set,decision,gate_json,previous_weights_json,proposed_weights_json,applied)
       VALUES(%s,%s,%s,%s,'Promoted',%s::jsonb,%s::jsonb,%s::jsonb,TRUE);""",
       (promotion_id,cycle_id,current.get("model_version"),new_id,json.dumps(gate,default=str),json.dumps(current.get("weights_json") or {}),json.dumps(proposed)))
    return {"applied":True,"promotion_id":promotion_id,"from_weight_set":current.get("model_version"),"to_weight_set":new_id,"weights":proposed}

def run_adaptive_learning_cycle(cycle_name:str="v2.19.0 autonomous adaptive learning cycle",save_result:bool=True)->Dict[str,Any]:
    try:
      factors=get_factor_effectiveness_report(); weights=get_weight_recommendations(); dataset=_dataset()
      if not factors.get("success") or not weights.get("success"):
        return {"success":False,"learning_version":LEARNING_VERSION,"factor_report":factors,"weight_report":weights}
      selection=run_selection_intelligence_analysis(save_result=True)
      proposed=_candidate(weights)
      sim=run_weight_simulation(test_weights=proposed,simulation_name="v2.19.0 adaptive promotion candidate",notes="Automatic promotion-gate validation.",save_result=True,simulation_group="v2.19.0 promotion gate")
      gate=_gate(dataset,sim)
      cycle_id=f"learn-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
      current=_active_weight_row(); promotion={"applied":False,"reason":"Promotion gate not authorised."}
      if gate.get("promotion_authorised"):
        promotion=_promote(cycle_id,current,proposed,gate)
      result={"success":True,"provider":"PostgreSQL","learning_version":LEARNING_VERSION,"model_version":MODEL_VERSION,"cycle_id":cycle_id,"cycle_name":cycle_name,"generated_at":datetime.now(timezone.utc).isoformat(),"analysis_only":not bool(promotion.get("applied")),"weights_changed_by_this_cycle":bool(promotion.get("applied")),"production_weights_active":True,"automatic_weight_changes_enabled":AUTO_PROMOTION_ENABLED,"historical_learning_retained":True,"reconstructed_full_field_history_required":False,"native_full_field_capture_active":True,"dataset":dataset,"active_weight_set_before_cycle":current,"proposed_weights":proposed,"factor_report":factors,"weight_report":weights,"simulation_report":sim,"selection_report":selection,"promotion_gate":gate,"promotion":promotion,"safety_note":"Automatic promotion only occurs after every configured gate passes for the required number of consecutive cycles. A rollback set is retained."}
      if save_result:
        execute_sql("""INSERT INTO rrt_learning_cycles(cycle_id,cycle_name,learning_version,model_version,dataset_json,factor_report_json,weight_report_json,simulation_report_json,selection_report_json,recommendations_json,cycle_json)
          VALUES(%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb);""",
          (cycle_id,cycle_name,LEARNING_VERSION,MODEL_VERSION,json.dumps(dataset,default=str),json.dumps(factors,default=str),json.dumps(weights,default=str),json.dumps(sim,default=str),json.dumps(selection,default=str),json.dumps(weights.get("recommendations") or [],default=str),json.dumps(result,default=str)))
      return result
    except Exception as e:
      return {"success":False,"provider":"PostgreSQL","learning_version":LEARNING_VERSION,"model_version":MODEL_VERSION,"error":str(e)}

def get_learning_cycle_report(cycle_id:Optional[str]=None)->Dict[str,Any]:
    row=fetch_one("SELECT cycle_json FROM rrt_learning_cycles WHERE cycle_id=%s;" if cycle_id else "SELECT cycle_json FROM rrt_learning_cycles ORDER BY created_at DESC LIMIT 1;",(cycle_id,) if cycle_id else ())
    return (row or {}).get("cycle_json") or {"success":False,"message":"No learning cycle found."}

def get_learning_cycle_history(limit:int=20)->Dict[str,Any]:
    rows=fetch_all("SELECT cycle_id,cycle_name,learning_version,model_version,cycle_json->'promotion_gate'->>'decision' AS decision,cycle_json->'promotion'->>'applied' AS promoted,created_at FROM rrt_learning_cycles ORDER BY created_at DESC LIMIT %s;",(max(1,min(limit,100)),))
    return {"success":True,"learning_version":LEARNING_VERSION,"cycle_count":len(rows),"cycles":rows}

def get_learning_recommendation_history(limit:int=100)->Dict[str,Any]:
    rows=fetch_all("SELECT cycle_id,factor,current_weight,recommended_weight,change_amount,expected_improvement,confidence_pct,status,rationale,created_at FROM rrt_factor_recommendations ORDER BY created_at DESC LIMIT %s;",(max(1,min(limit,500)),))
    return {"success":True,"learning_version":LEARNING_VERSION,"recommendation_count":len(rows),"recommendations":rows}

def get_adaptive_learning_summary()->Dict[str,Any]:
    summary=fetch_one("SELECT COUNT(*) AS cycle_count,MAX(created_at) AS latest_cycle_at FROM rrt_learning_cycles;") or {}
    active=_active_weight_row(); audit=fetch_one("SELECT COUNT(*) AS promotion_count,MAX(created_at) AS latest_promotion_at FROM rrt_weight_promotion_audit WHERE applied IS TRUE;") or {}
    return {"success":True,"learning_version":LEARNING_VERSION,"model_version":MODEL_VERSION,"summary":summary,"active_weight_set":active,"automatic_weight_changes_enabled":AUTO_PROMOTION_ENABLED,"promotion_summary":audit,"dataset":_dataset(),"weights_changed_by_this_request":False,"historical_learning_retained":True,"native_full_field_capture_active":True,"reconstructed_full_field_history_required":False}
