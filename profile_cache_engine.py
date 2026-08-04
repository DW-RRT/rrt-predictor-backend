from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta, timezone
import json, os, uuid

from database import execute_sql, fetch_all, fetch_one
from punting_form_client import make_request, get_meeting_form, simplify_form_response

PROFILE_VERSION = "2.21.0"
HORSE_CACHE_HOURS = int(os.getenv("RRT_HORSE_PROFILE_CACHE_HOURS", "24"))
STRIKE_CACHE_HOURS = int(os.getenv("RRT_STRIKE_RATE_CACHE_HOURS", "24"))
AUTO_STRIKE_RATE_REFRESH = os.getenv("RRT_AUTO_STRIKE_RATE_REFRESH", "true").lower() == "true"


def _f(v: Any, d: float = 0.0) -> float:
    try: return d if v is None or v == "" else float(v)
    except Exception: return d

def _i(v: Any, d: int = 0) -> int:
    try: return d if v is None or v == "" else int(float(v))
    except Exception: return d

def _name(v: Any) -> str:
    return " ".join(str(v or "").strip().split())

def _key(v: Any) -> str:
    return _name(v).upper().replace(".", "").replace("'", "").replace("’", "")

def _payload(response: Any) -> List[Dict[str, Any]]:
    if not isinstance(response, dict): return []
    data=response.get("payLoad") or response.get("payload") or []
    return data if isinstance(data, list) else [data] if isinstance(data, dict) else []

def _extract_runner_history(runner: Dict[str, Any]) -> List[Dict[str, Any]]:
    for field in ("historical_forms","historicalForms","forms","previous_runs","previousRuns"):
        value=runner.get(field)
        if isinstance(value,list): return [x for x in value if isinstance(x,dict)]
    return []

def _position(row: Dict[str,Any]) -> Optional[int]:
    for k in ("position","finishPosition","finishingPosition","placing","result"):
        v=row.get(k)
        if v not in (None,""):
            try: return int(float(v))
            except Exception: pass
    return None

def _run_date(row: Dict[str,Any]) -> Optional[str]:
    for k in ("meetingDate","raceDate","date","startDate"):
        v=row.get(k)
        if v: return str(v).split("T")[0][:10]
    return None

def _horse_id(runner: Dict[str,Any]) -> int:
    for k in ("runner_id","runnerId","horseId","horse_id","entityId"):
        n=_i(runner.get(k),0)
        if n: return n
    return 0

def _horse_name(runner: Dict[str,Any]) -> str:
    return _name(runner.get("horse_name") or runner.get("runner") or runner.get("name") or runner.get("horseName"))

def _trainer(runner: Dict[str,Any]) -> str:
    return _name(runner.get("trainer") or runner.get("trainerName"))

def _jockey(runner: Dict[str,Any]) -> str:
    return _name(runner.get("jockey") or runner.get("jockeyName"))

def _fresh(table: str, key_col: str, key: Any, hours: int) -> Optional[Dict[str,Any]]:
    return fetch_one(f"SELECT * FROM {table} WHERE {key_col}=%s AND refreshed_at >= NOW() - (%s || ' hours')::interval LIMIT 1;",(key,hours))

def cache_profiles_from_form_data(form_data: Dict[str,Any], meeting_id: Optional[int]=None) -> Dict[str,Any]:
    saved_profiles=saved_runs=0; failures=[]
    for race in form_data.get("races") or []:
        race_id=race.get("race_id"); race_number=race.get("race_number")
        for runner in race.get("runners") or []:
            horse=_horse_name(runner)
            if not horse: continue
            hid=_horse_id(runner); history=_extract_runner_history(runner)
            try:
                for run in history:
                    p=_position(run); rd=_run_date(run)
                    track=_name(run.get("track") or run.get("trackName") or run.get("venue"))
                    dist=_i(run.get("distance") or run.get("distanceM"),0)
                    unique=f"{hid or _key(horse)}|{rd or ''}|{_key(track)}|{dist}|{p or ''}"
                    execute_sql("""INSERT INTO rrt_horse_history(horse_id,horse_name,trainer,run_key,run_date,track,distance_m,position,raw_json,source,updated_at)
                      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'Punting Form /v2/form/form',NOW())
                      ON CONFLICT(run_key) DO UPDATE SET horse_name=EXCLUDED.horse_name,trainer=EXCLUDED.trainer,position=EXCLUDED.position,raw_json=EXCLUDED.raw_json,updated_at=NOW();""",
                      (hid or None,horse,_trainer(runner),unique,rd,track or None,dist or None,p,json.dumps(run,default=str)))
                    saved_runs += 1
                agg=fetch_one("""SELECT COUNT(*) starts,COUNT(*) FILTER(WHERE position=1) wins,COUNT(*) FILTER(WHERE position=2) seconds,
                  COUNT(*) FILTER(WHERE position=3) thirds,MAX(run_date) latest_run_date FROM rrt_horse_history
                  WHERE (horse_id=%s AND %s>0) OR (%s=0 AND UPPER(horse_name)=UPPER(%s));""",(hid,hid,hid,horse)) or {}
                starts=_i(agg.get('starts')); wins=_i(agg.get('wins')); seconds=_i(agg.get('seconds')); thirds=_i(agg.get('thirds'))
                if starts==0:
                    starts=_i(runner.get('starts') or runner.get('careerStarts')); wins=_i(runner.get('firsts') or runner.get('wins') or runner.get('careerWins'))
                    seconds=_i(runner.get('seconds') or runner.get('careerSeconds')); thirds=_i(runner.get('thirds') or runner.get('careerThirds'))
                place=wins+seconds+thirds
                execute_sql("""INSERT INTO rrt_horse_profiles(horse_id,horse_key,horse_name,trainer,career_starts,career_wins,career_seconds,career_thirds,
                  win_pct,place_pct,last10,latest_run_date,profile_json,source,refreshed_at,expires_at)
                  VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'Punting Form /v2/form/form',NOW(),NOW()+(%s||' hours')::interval)
                  ON CONFLICT(horse_key) DO UPDATE SET horse_id=COALESCE(EXCLUDED.horse_id,rrt_horse_profiles.horse_id),horse_name=EXCLUDED.horse_name,
                  trainer=EXCLUDED.trainer,career_starts=EXCLUDED.career_starts,career_wins=EXCLUDED.career_wins,career_seconds=EXCLUDED.career_seconds,
                  career_thirds=EXCLUDED.career_thirds,win_pct=EXCLUDED.win_pct,place_pct=EXCLUDED.place_pct,last10=EXCLUDED.last10,
                  latest_run_date=EXCLUDED.latest_run_date,profile_json=EXCLUDED.profile_json,refreshed_at=NOW(),expires_at=EXCLUDED.expires_at;""",
                  (hid or None,(f'ID:{hid}' if hid else f'NAME:{_key(horse)}'),horse,_trainer(runner) or None,starts,wins,seconds,thirds,
                   round(wins/starts*100,2) if starts else 0,round(place/starts*100,2) if starts else 0,runner.get('last10'),agg.get('latest_run_date'),json.dumps(runner,default=str),HORSE_CACHE_HOURS))
                saved_profiles += 1
            except Exception as e: failures.append({'horse':horse,'error':str(e)})
    return {'success':True,'profile_version':PROFILE_VERSION,'meeting_id':meeting_id,'horse_profiles_saved':saved_profiles,'historical_runs_saved':saved_runs,'failures':failures[:20]}

def _strike_rows(response: Dict[str,Any], entity_type: str) -> int:
    count=0
    for row in _payload(response):
        name=_name(row.get('entityName') or row.get('name')); eid=_i(row.get('entityId'),0)
        if not name: continue
        starts=_i(row.get('careerStarts')); wins=_i(row.get('careerWins')); seconds=_i(row.get('careerSeconds')); thirds=_i(row.get('careerThirds'))
        lstarts=_i(row.get('last100Starts')); lwins=_i(row.get('last100Wins')); lseconds=_i(row.get('last100Seconds')); lthirds=_i(row.get('last100Thirds'))
        execute_sql("""INSERT INTO rrt_entity_strike_rates(entity_type,entity_id,entity_key,entity_name,start_date,career_starts,career_wins,career_seconds,career_thirds,
          career_expected_wins,career_pl,career_turnover,last100_starts,last100_wins,last100_seconds,last100_thirds,last100_expected_wins,last100_pl,last100_turnover,
          career_win_pct,career_place_pct,last100_win_pct,last100_place_pct,raw_json,source,refreshed_at,expires_at)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'Punting Form /v2/form/strikerate',NOW(),NOW()+(%s||' hours')::interval)
          ON CONFLICT(entity_type,entity_key) DO UPDATE SET entity_id=COALESCE(EXCLUDED.entity_id,rrt_entity_strike_rates.entity_id),entity_name=EXCLUDED.entity_name,
          start_date=EXCLUDED.start_date,career_starts=EXCLUDED.career_starts,career_wins=EXCLUDED.career_wins,career_seconds=EXCLUDED.career_seconds,
          career_thirds=EXCLUDED.career_thirds,career_expected_wins=EXCLUDED.career_expected_wins,career_pl=EXCLUDED.career_pl,career_turnover=EXCLUDED.career_turnover,
          last100_starts=EXCLUDED.last100_starts,last100_wins=EXCLUDED.last100_wins,last100_seconds=EXCLUDED.last100_seconds,last100_thirds=EXCLUDED.last100_thirds,
          last100_expected_wins=EXCLUDED.last100_expected_wins,last100_pl=EXCLUDED.last100_pl,last100_turnover=EXCLUDED.last100_turnover,
          career_win_pct=EXCLUDED.career_win_pct,career_place_pct=EXCLUDED.career_place_pct,last100_win_pct=EXCLUDED.last100_win_pct,
          last100_place_pct=EXCLUDED.last100_place_pct,raw_json=EXCLUDED.raw_json,refreshed_at=NOW(),expires_at=EXCLUDED.expires_at;""",
          (entity_type,eid or None,(f'ID:{eid}' if eid else f'NAME:{_key(name)}'),name,str(row.get('startDate') or '')[:10] or None,starts,wins,seconds,thirds,
           _f(row.get('careerExpectedWins')),_f(row.get('careerPL')),_f(row.get('careerTurnvoer') or row.get('careerTurnover')),lstarts,lwins,lseconds,lthirds,
           _f(row.get('last100ExpectedWins')),_f(row.get('last100PL')),_f(row.get('last100Turnvoer') or row.get('last100Turnover')),
           round(wins/starts*100,2) if starts else 0,round((wins+seconds+thirds)/starts*100,2) if starts else 0,
           round(lwins/lstarts*100,2) if lstarts else 0,round((lwins+lseconds+lthirds)/lstarts*100,2) if lstarts else 0,json.dumps(row,default=str),STRIKE_CACHE_HOURS))
        count += 1
    return count

def refresh_strike_rates(meeting_id: Optional[int]=None, start_date: Optional[str]=None, force: bool=False) -> Dict[str,Any]:
    result={'success':True,'profile_version':PROFILE_VERSION,'trainer_saved':0,'jockey_saved':0,'attempts':[]}
    for entity in ('Trainer','Jockey'):
        params={}
        if meeting_id is not None: params['meetingId']=meeting_id
        if start_date: params['startDate']=start_date
        params['entityType']=entity
        try:
            response=make_request('/v2/form/strikerate',params)
            saved=_strike_rows(response,entity.lower())
            result[f'{entity.lower()}_saved']=saved
            result['attempts'].append({'entity_type':entity,'success':True,'saved':saved})
        except Exception as e:
            result['attempts'].append({'entity_type':entity,'success':False,'error':str(e)})
    result['success']=any(x.get('success') for x in result['attempts'])
    return result

def refresh_meeting_profiles(meeting_id:int,runs:int=10,force:bool=False,include_strike_rates:bool=True)->Dict[str,Any]:
    refresh_id=f"profile-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    try:
        raw=get_meeting_form(meeting_id=meeting_id,race_number=0,runs=runs); form=simplify_form_response(raw)
        horse=cache_profiles_from_form_data(form,meeting_id)
        strike=refresh_strike_rates(meeting_id=meeting_id) if include_strike_rates else {'success':True,'skipped':True}
        result={'success':True,'profile_version':PROFILE_VERSION,'refresh_id':refresh_id,'meeting_id':meeting_id,'horse':horse,'strike_rates':strike,'prediction_required':False}
    except Exception as e: result={'success':False,'profile_version':PROFILE_VERSION,'refresh_id':refresh_id,'meeting_id':meeting_id,'error':str(e)}
    try: execute_sql("INSERT INTO rrt_profile_refresh_runs(refresh_id,meeting_id,status,result_json,completed_at) VALUES(%s,%s,%s,%s::jsonb,NOW());",(refresh_id,meeting_id,'completed' if result.get('success') else 'failed',json.dumps(result,default=str)))
    except Exception: pass
    return result

def enrich_form_data_with_cached_profiles(form_data:Dict[str,Any])->Dict[str,Any]:
    matched={'horse':0,'trainer':0,'jockey':0}
    races=[]
    for race in form_data.get('races') or []:
        runners=[]
        for r in race.get('runners') or []:
            hid=_horse_id(r); horse=_horse_name(r); tr=_trainer(r); jo=_jockey(r)
            hp=fetch_one("SELECT * FROM rrt_horse_profiles WHERE horse_key=%s LIMIT 1;",(f'ID:{hid}' if hid else f'NAME:{_key(horse)}',)) or {}
            tp=fetch_one("SELECT * FROM rrt_entity_strike_rates WHERE entity_type='trainer' AND entity_key=%s LIMIT 1;",(f'NAME:{_key(tr)}',)) or {} if tr else {}
            jp=fetch_one("SELECT * FROM rrt_entity_strike_rates WHERE entity_type='jockey' AND entity_key=%s LIMIT 1;",(f'NAME:{_key(jo)}',)) or {} if jo else {}
            matched['horse']+=bool(hp); matched['trainer']+=bool(tp); matched['jockey']+=bool(jp)
            runners.append({**r,'historical_horse_profile':hp,'historical_trainer_profile':tp,'historical_jockey_profile':jp,'profile_cache_version':PROFILE_VERSION})
        races.append({**race,'runners':runners})
    return {**form_data,'races':races,'profile_cache_merge':matched}

def get_profile_cache_summary()->Dict[str,Any]:
    h=fetch_one("SELECT COUNT(*) profile_count,COALESCE(SUM(career_starts),0) career_starts,MAX(refreshed_at) latest_refresh FROM rrt_horse_profiles;") or {}
    runs=fetch_one("SELECT COUNT(*) history_rows,COUNT(DISTINCT horse_key) horse_count,MAX(run_date) latest_run_date FROM (SELECT COALESCE('ID:'||horse_id::text,'NAME:'||UPPER(horse_name)) horse_key,run_date FROM rrt_horse_history) x;") or {}
    entities=fetch_all("SELECT entity_type,COUNT(*) profile_count,MAX(refreshed_at) latest_refresh FROM rrt_entity_strike_rates GROUP BY entity_type ORDER BY entity_type;")
    return {'success':True,'profile_version':PROFILE_VERSION,'horse_profiles':h,'horse_history':runs,'strike_rate_profiles':entities,'automatic_profile_cache':True}

def get_historical_horse_leaderboard(limit:int=20,min_starts:int=5)->Dict[str,Any]:
    rows=fetch_all("""SELECT horse_name horse,trainer,career_starts starts,career_wins wins,(career_wins+career_seconds+career_thirds) places,
      win_pct,place_pct,last10,latest_run_date,source,refreshed_at FROM rrt_horse_profiles WHERE career_starts >= %s
      ORDER BY place_pct DESC,win_pct DESC,career_starts DESC,horse_name LIMIT %s;""",(min_starts,max(1,min(limit,100))))
    return {'success':True,'profile_version':PROFILE_VERSION,'source':'Punting Form /v2/form/form','limit':limit,'min_starts':min_starts,'horses':[{**r,'rank':i+1} for i,r in enumerate(rows)]}

def get_strike_rate_leaderboard(entity_type:str,limit:int=20,min_starts:int=100,period:str='last100')->Dict[str,Any]:
    et=entity_type.lower(); period='career' if period.lower()=='career' else 'last100'
    s='career_starts' if period=='career' else 'last100_starts'; w='career_wins' if period=='career' else 'last100_wins'; sec='career_seconds' if period=='career' else 'last100_seconds'; th='career_thirds' if period=='career' else 'last100_thirds'; wp='career_win_pct' if period=='career' else 'last100_win_pct'; pp='career_place_pct' if period=='career' else 'last100_place_pct'
    rows=fetch_all(f"SELECT entity_name,{s} starts,{w} wins,({w}+{sec}+{th}) places,{wp} win_pct,{pp} place_pct,career_pl,last100_pl,source,refreshed_at FROM rrt_entity_strike_rates WHERE entity_type=%s AND {s}>=%s ORDER BY {wp} DESC,{pp} DESC,{s} DESC,entity_name LIMIT %s;",(et,min_starts,max(1,min(limit,100))))
    return {'success':True,'profile_version':PROFILE_VERSION,'entity_type':et,'period':period,'source':'Punting Form /v2/form/strikerate','profiles':[{**r,'rank':i+1} for i,r in enumerate(rows)]}

def get_entity_profile(entity_type:str,entity_name:Optional[str]=None,entity_id:Optional[int]=None)->Dict[str,Any]:
    et=entity_type.lower()
    if et=='horse':
        row=fetch_one("SELECT * FROM rrt_horse_profiles WHERE (horse_id=%s AND %s IS NOT NULL) OR UPPER(horse_name)=UPPER(%s) ORDER BY refreshed_at DESC LIMIT 1;",(entity_id,entity_id,entity_name or ''))
    else:
        row=fetch_one("SELECT * FROM rrt_entity_strike_rates WHERE entity_type=%s AND ((entity_id=%s AND %s IS NOT NULL) OR UPPER(entity_name)=UPPER(%s)) ORDER BY refreshed_at DESC LIMIT 1;",(et,entity_id,entity_id,entity_name or ''))
    return {'success':bool(row),'profile_version':PROFILE_VERSION,'entity_type':et,'profile':row or {},'message':None if row else 'Profile not found in cache.'}
