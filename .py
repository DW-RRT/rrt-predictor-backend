warning: in the working copy of 'performance_reports.py', LF will be replaced by CRLF the next time Git touches it
[1mdiff --git a/performance_reports.py b/performance_reports.py[m
[1mindex 384afaa..34f8793 100644[m
[1m--- a/performance_reports.py[m
[1m+++ b/performance_reports.py[m
[36m@@ -1152,7 +1152,166 @@[m [mdef get_each_way_leaderboards([m
 [m
         trainers = entity_query(trainer_expr, "trainer", max(int(min_runners), MIN_TRAINER_RUNNERS))[m
         jockeys = entity_query(jockey_expr, "jockey", max(int(min_runners), MIN_JOCKEY_RUNNERS))[m
[31m-        horses = entity_query(horse_expr, "horse", MIN_HORSE_RUNS, HISTORICAL_HORSE_LIMIT)[m
[32m+[m
[32m+[m[32m        # Historical horse performance must be based on distinct actual race starts,[m
[32m+[m[32m        # not on repeated model-version snapshots for the same horse and race.[m
[32m+[m[32m        horses = fetch_all([m
[32m+[m[32m            f"""[m
[32m+[m[32m            WITH completed_rows AS ([m
[32m+[m[32m                SELECT[m
[32m+[m[32m                    id,[m
[32m+[m[32m                    meeting_id,[m
[32m+[m[32m                    meeting_date,[m
[32m+[m[32m                    race_id,[m
[32m+[m[32m                    race_number,[m
[32m+[m[32m                    runner_id,[m
[32m+[m[32m                    tab_number,[m
[32m+[m[32m                    updated_at,[m
[32m+[m[32m                    created_at,[m
[32m+[m[32m                    {horse_expr} AS horse,[m
[32m+[m[32m                    {trainer_expr} AS trainer,[m
[32m+[m[32m                    actual_position,[m
[32m+[m[32m                    final_score,[m
[32m+[m[32m                    confidence,[m
[32m+[m[32m                    ROW_NUMBER() OVER ([m
[32m+[m[32m                        PARTITION BY[m
[32m+[m[32m                            meeting_id,[m
[32m+[m[32m                            COALESCE(race_id::TEXT, race_number::TEXT, ''),[m
[32m+[m[32m                            CASE[m
[32m+[m[32m                                WHEN runner_id IS NOT NULL AND runner_id > 0[m
[32m+[m[32m                                    THEN 'ID:' || runner_id::TEXT[m
[32m+[m[32m                                ELSE 'NAME:' || UPPER(TRIM(COALESCE([m
[32m+[m[32m                                    {horse_expr},[m
[32m+[m[32m                                    ''[m
[32m+[m[32m                                ))) || '|TAB:' || COALESCE(tab_number::TEXT, '')[m
[32m+[m[32m                            END[m
[32m+[m[32m                        ORDER BY[m
[32m+[m[32m                            updated_at DESC NULLS LAST,[m
[32m+[m[32m                            created_at DESC NULLS LAST,[m
[32m+[m[32m                            id DESC[m
[32m+[m[32m                    ) AS start_snapshot_rank[m
[32m+[m[32m                FROM rrt_runner_factor_snapshots[m
[32m+[m[32m                WHERE actual_position IS NOT NULL[m
[32m+[m[32m                  AND {horse_expr} IS NOT NULL[m
[32m+[m[32m                  AND UPPER({horse_expr}) NOT IN ('N/A', 'UNKNOWN', 'NONE')[m
[32m+[m[32m            ),[m
[32m+[m[32m            distinct_starts AS ([m
[32m+[m[32m                SELECT[m
[32m+[m[32m                    meeting_id,[m
[32m+[m[32m                    meeting_date,[m
[32m+[m[32m                    race_id,[m
[32m+[m[32m                    race_number,[m
[32m+[m[32m                    runner_id,[m
[32m+[m[32m                    tab_number,[m
[32m+[m[32m                    horse,[m
[32m+[m[32m                    trainer,[m
[32m+[m[32m                    actual_position,[m
[32m+[m[32m                    final_score,[m
[32m+[m[32m                    confidence,[m
[32m+[m[32m                    updated_at,[m
[32m+[m[32m                    created_at[m
[32m+[m[32m                FROM completed_rows[m
[32m+[m[32m                WHERE start_snapshot_rank = 1[m
[32m+[m[32m            ),[m
[32m+[m[32m            horse_rollup AS ([m
[32m+[m[32m                SELECT[m
[32m+[m[32m                    COALESCE([m
[32m+[m[32m                        CASE[m
[32m+[m[32m                            WHEN runner_id IS NOT NULL AND runner_id > 0[m
[32m+[m[32m                                THEN 'ID:' || runner_id::TEXT[m
[32m+[m[32m                            ELSE NULL[m
[32m+[m[32m                        END,[m
[32m+[m[32m                        'NAME:' || UPPER(TRIM(horse))[m
[32m+[m[32m                    ) AS horse_key,[m
[32m+[m[32m                    MAX(horse) AS horse,[m
[32m+[m[32m                    COUNT(*) AS runner_count,[m
[32m+[m[32m                    SUM(CASE WHEN actual_position = 1 THEN 1 ELSE 0 END) AS win_count,[m
[32m+[m[32m                    SUM(CASE WHEN actual_position BETWEEN 1 AND 3 THEN 1 ELSE 0 END) AS place_count,[m
[32m+[m[32m                    ROUND([m
[32m+[m[32m                        (SUM(CASE WHEN actual_position = 1 THEN 1 ELSE 0 END)::NUMERIC[m
[32m+[m[32m                        / NULLIF(COUNT(*), 0)) * 100,[m
[32m+[m[32m                        2[m
[32m+[m[32m                    ) AS win_strike_rate,[m
[32m+[m[32m                    ROUND([m
[32m+[m[32m                        (SUM(CASE WHEN actual_position BETWEEN 1 AND 3 THEN 1 ELSE 0 END)::NUMERIC[m
[32m+[m[32m                        / NULLIF(COUNT(*), 0)) * 100,[m
[32m+[m[32m                        2[m
[32m+[m[32m                    ) AS place_strike_rate,[m
[32m+[m[32m                    ROUND(AVG(final_score), 2) AS avg_final_score,[m
[32m+[m[32m                    ROUND(AVG(confidence), 2) AS avg_confidence[m
[32m+[m[32m                FROM distinct_starts[m
[32m+[m[32m                GROUP BY[m
[32m+[m[32m                    COALESCE([m
[32m+[m[32m                        CASE[m
[32m+[m[32m                            WHEN runner_id IS NOT NULL AND runner_id > 0[m
[32m+[m[32m                                THEN 'ID:' || runner_id::TEXT[m
[32m+[m[32m                            ELSE NULL[m
[32m+[m[32m                        END,[m
[32m+[m[32m                        'NAME:' || UPPER(TRIM(horse))[m
[32m+[m[32m                    )[m
[32m+[m[32m                HAVING COUNT(*) >= %s[m
[32m+[m[32m            ),[m
[32m+[m[32m            latest_trainer AS ([m
[32m+[m[32m                SELECT DISTINCT ON ([m
[32m+[m[32m                    COALESCE([m
[32m+[m[32m                        CASE[m
[32m+[m[32m                            WHEN runner_id IS NOT NULL AND runner_id > 0[m
[32m+[m[32m                                THEN 'ID:' || runner_id::TEXT[m
[32m+[m[32m                            ELSE NULL[m
[32m+[m[32m                        END,[m
[32m+[m[32m                        'NAME:' || UPPER(TRIM(horse))[m
[32m+[m[32m                    )[m
[32m+[m[32m                )[m
[32m+[m[32m                    COALESCE([m
[32m+[m[32m                        CASE[m
[32m+[m[32m                            WHEN runner_id IS NOT NULL AND runner_id > 0[m
[32m+[m[32m                                THEN 'ID:' || runner_id::TEXT[m
[32m+[m[32m                            ELSE NULL[m
[32m+[m[32m                        END,[m
[32m+[m[32m                        'NAME:' || UPPER(TRIM(horse))[m
[32m+[m[32m                    ) AS horse_key,[m
[32m+[m[32m                    trainer[m
[32m+[m[32m                FROM distinct_starts[m
[32m+[m[32m                WHERE trainer IS NOT NULL[m
[32m+[m[32m                  AND UPPER(trainer) NOT IN ('N/A', 'UNKNOWN', 'NONE')[m
[32m+[m[32m                ORDER BY[m
[32m+[m[32m                    COALESCE([m
[32m+[m[32m                        CASE[m
[32m+[m[32m                            WHEN runner_id IS NOT NULL AND runner_id > 0[m
[32m+[m[32m                                THEN 'ID:' || runner_id::TEXT[m
[32m+[m[32m                            ELSE NULL[m
[32m+[m[32m                        END,[m
[32m+[m[32m                        'NAME:' || UPPER(TRIM(horse))[m
[32m+[m[32m                    ),[m
[32m+[m[32m                    meeting_date DESC NULLS LAST,[m
[32m+[m[32m                    updated_at DESC NULLS LAST,[m
[32m+[m[32m                    created_at DESC NULLS LAST[m
[32m+[m[32m            )[m
[32m+[m[32m            SELECT[m
[32m+[m[32m                hr.horse,[m
[32m+[m[32m                COALESCE(lt.trainer, 'Not recorded') AS trainer,[m
[32m+[m[32m                hr.runner_count,[m
[32m+[m[32m                hr.win_count,[m
[32m+[m[32m                hr.place_count,[m
[32m+[m[32m                hr.win_strike_rate,[m
[32m+[m[32m                hr.place_strike_rate,[m
[32m+[m[32m                hr.avg_final_score,[m
[32m+[m[32m                hr.avg_confidence[m
[32m+[m[32m            FROM horse_rollup hr[m
[32m+[m[32m            LEFT JOIN latest_trainer lt[m
[32m+[m[32m              ON lt.horse_key = hr.horse_key[m
[32m+[m[32m            ORDER BY[m
[32m+[m[32m                hr.place_strike_rate DESC,[m
[32m+[m[32m                hr.win_strike_rate DESC,[m
[32m+[m[32m                hr.place_count DESC,[m
[32m+[m[32m                hr.win_count DESC,[m
[32m+[m[32m                hr.runner_count DESC,[m
[32m+[m[32m                hr.avg_final_score DESC,[m
[32m+[m[32m                hr.horse ASC[m
[32m+[m[32m            LIMIT %s;[m
[32m+[m[32m            """,[m
[32m+[m[32m            (MIN_HORSE_RUNS, HISTORICAL_HORSE_LIMIT),[m
[32m+[m[32m        )[m
         for horse in horses:[m
             horse["evidence_status"] = "Established" if _to_int(horse.get("runner_count")) >= 5 else "Emerging"[m
 [m
[36m@@ -1195,8 +1354,8 @@[m [mdef get_each_way_leaderboards([m
             },[m
             "limit": limit,[m
             "historical_horse_limit": HISTORICAL_HORSE_LIMIT,[m
[31m-            "ranking_method": "All completed runner-factor rows; ranked by place strike rate, then win strike rate and sample size after minimum sample thresholds.",[m
[31m-            "horse_ranking_note": "This is an aggregated historical horse leaderboard across completed runs. It is separate from the per-meeting Top 20 prediction ranking.",[m
[32m+[m[32m            "ranking_method": "Trainer, jockey and combination leaderboards use completed runner-factor rows. Historical horses are deduplicated to one row per actual start before win/place rates are calculated.",[m
[32m+[m[32m            "horse_ranking_note": "This is an aggregated historical horse leaderboard across distinct actual starts. Repeated model-version snapshots for the same meeting, race and runner are counted once. It is separate from the per-meeting Top 20 prediction ranking.",[m
             "dataset": totals,[m
             "top_trainers": _rank_rows(trainers),[m
             "top_jockeys": _rank_rows(jockeys),[m
[36m@@ -1376,8 +1535,8 @@[m [mdef generate_learning_report_html() -> str:[m
         '<h3>Top 10 Jockeys</h3>', _html_table(['Rank','Jockey','Runs','Wins','Places','Win %','Place %','Avg Score','Avg Confidence'], [[i.get('rank'),i.get('jockey'),i.get('runner_count'),i.get('win_count'),i.get('place_count'),_pct(i.get('win_strike_rate')),_pct(i.get('place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in ((report.get('each_way_leaderboards') or {}).get('top_jockeys') or [])[:10]]),[m
         '<h3>Top 10 Trainer / Jockey Combinations</h3>', _html_table(['Rank','Combination','Runs','Wins','Places','Win %','Place %','Avg Score','Avg Confidence'], [[i.get('rank'),i.get('trainer_jockey_combination'),i.get('runner_count'),i.get('win_count'),i.get('place_count'),_pct(i.get('win_strike_rate')),_pct(i.get('place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in ((report.get('each_way_leaderboards') or {}).get('top_trainer_jockey_combinations') or [])[:10]]),[m
         '<h3>Top 20 Historical Horse Performance</h3>',[m
[31m-        '<div class="note">Aggregated historical performance across completed runner-factor records. This table is separate from the per-meeting Top 20 prediction ranking. Emerging = 2-4 completed runs; Established = 5 or more completed runs.</div>',[m
[31m-        (_html_table(['Rank','Horse','Status','Runs','Wins','Places','Win %','Place %','Avg Score','Avg Confidence'], [[i.get('rank'),i.get('horse'),i.get('evidence_status'),i.get('runner_count'),i.get('win_count'),i.get('place_count'),_pct(i.get('win_strike_rate')),_pct(i.get('place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in ((report.get('each_way_leaderboards') or {}).get('top_horses') or [])[:20]]) if ((report.get('each_way_leaderboards') or {}).get('top_horses') or []) else '<div class="note">Insufficient historical horse performance data available. A minimum of two completed runs is required before inclusion.</div>'),[m
[32m+[m[32m        '<div class="note">Aggregated historical performance across distinct actual race starts. Repeated model-version snapshots for the same horse and race are counted once. The Trainer shown is from the latest completed recorded start. This table is separate from the per-meeting Top 20 prediction ranking. Emerging = 2-4 completed runs; Established = 5 or more completed runs.</div>',[m
[32m+[m[32m        (_html_table(['Rank','Horse','Trainer','Status','Runs','Wins','Places','Win %','Place %','Avg Score','Avg Confidence'], [[i.get('rank'),i.get('horse'),i.get('trainer'),i.get('evidence_status'),i.get('runner_count'),i.get('win_count'),i.get('place_count'),_pct(i.get('win_strike_rate')),_pct(i.get('place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in ((report.get('each_way_leaderboards') or {}).get('top_horses') or [])[:20]]) if ((report.get('each_way_leaderboards') or {}).get('top_horses') or []) else '<div class="note">Insufficient historical horse performance data available. A minimum of two distinct completed starts is required before inclusion.</div>'),[m
         '<h2>Evidence-Based Factor Analysis</h2>',[m
         '<div class="note">This section compares completed runner factor scores against actual results. It reports against the active v2.20.1 production weights. Automatic weight changes are disabled, and all future proposals remain inactive until manually reviewed and approved.</div>',[m
         '<h3>Factor Effectiveness Ranking</h3>',[m
[36m@@ -1484,11 +1643,15 @@[m [mdef generate_learning_report_pdf_bytes() -> bytes:[m
     story.append(Paragraph("Top 10 Trainer / Jockey Combinations", styles["RRTHeading"]))[m
     story.append(t(["Rank","Combination","Runs","Wins","Places","Win %","Place %","Avg Score","Avg Conf"], [[i.get('rank'),i.get('trainer_jockey_combination'),i.get('runner_count'),i.get('win_count'),i.get('place_count'),_pct(i.get('win_strike_rate')),_pct(i.get('place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in (leaderboards.get('top_trainer_jockey_combinations') or [])[:10]]))[m
     story.append(Paragraph("Top 20 Historical Horse Performance", styles["RRTHeading"]))[m
[31m-    story.append(Paragraph("Aggregated historical performance across completed runner-factor records. This table is separate from the per-meeting Top 20 prediction ranking. Emerging = 2-4 completed runs; Established = 5 or more completed runs.", styles["BodyText"]))[m
[32m+[m[32m    story.append(Paragraph("Aggregated historical performance across distinct actual race starts. Repeated model-version snapshots for the same horse and race are counted once. The Trainer shown is from the latest completed recorded start. This table is separate from the per-meeting Top 20 prediction ranking. Emerging = 2-4 completed runs; Established = 5 or more completed runs.", styles["BodyText"]))[m
     if leaderboards.get('top_horses'):[m
[31m-        story.append(t(["Rank","Horse","Status","Runs","Wins","Places","Win %","Place %","Avg Score","Avg Conf"], [[i.get('rank'),i.get('horse'),i.get('evidence_status'),i.get('runner_count'),i.get('win_count'),i.get('place_count'),_pct(i.get('win_strike_rate')),_pct(i.get('place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in (leaderboards.get('top_horses') or [])[:20]]))[m
[32m+[m[32m        story.append(t([m
[32m+[m[32m            ["Rank","Horse","Trainer","Status","Runs","Wins","Places","Win %","Place %","Avg Score","Avg Conf"],[m
[32m+[m[32m            [[i.get('rank'),i.get('horse'),i.get('trainer'),i.get('evidence_status'),i.get('runner_count'),i.get('win_count'),i.get('place_count'),_pct(i.get('win_strike_rate')),_pct(i.get('place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in (leaderboards.get('top_horses') or [])[:20]],[m
[32m+[m[32m            [0.7*cm, 2.6*cm, 2.8*cm, 1.6*cm, 0.8*cm, 0.8*cm, 0.9*cm, 1.1*cm, 1.1*cm, 1.3*cm, 1.3*cm],[m
[32m+[m[32m        ))[m
     else:[m
[31m-        story.append(Paragraph("Insufficient historical horse performance data available. A minimum of two completed runs is required before inclusion.", styles["BodyText"]))[m
[32m+[m[32m        story.append(Paragraph("Insufficient historical horse performance data available. A minimum of two distinct completed starts is required before inclusion.", styles["BodyText"]))[m
     story.append(PageBreak())[m
     story.append(Paragraph("Evidence-Based Factor Analysis", styles["RRTHeading"]))[m
     story.append(Paragraph("This section compares completed runner factor scores against actual results. It reports against the active v2.20.1 production weights. Automatic weight changes are disabled, and all future proposals remain inactive until manually reviewed and approved.", styles["BodyText"]))[m
warning: in the working copy of 'performance_reports.py', LF will be replaced by CRLF the next time Git touches it
[1mdiff --git a/performance_reports.py b/performance_reports.py[m
[1mindex 384afaa..34f8793 100644[m
[1m--- a/performance_reports.py[m
[1m+++ b/performance_reports.py[m
[36m@@ -1152,7 +1152,166 @@[m [mdef get_each_way_leaderboards([m
 [m
         trainers = entity_query(trainer_expr, "trainer", max(int(min_runners), MIN_TRAINER_RUNNERS))[m
         jockeys = entity_query(jockey_expr, "jockey", max(int(min_runners), MIN_JOCKEY_RUNNERS))[m
[31m-        horses = entity_query(horse_expr, "horse", MIN_HORSE_RUNS, HISTORICAL_HORSE_LIMIT)[m
[32m+[m
[32m+[m[32m        # Historical horse performance must be based on distinct actual race starts,[m
[32m+[m[32m        # not on repeated model-version snapshots for the same horse and race.[m
[32m+[m[32m        horses = fetch_all([m
[32m+[m[32m            f"""[m
[32m+[m[32m            WITH completed_rows AS ([m
[32m+[m[32m                SELECT[m
[32m+[m[32m                    id,[m
[32m+[m[32m                    meeting_id,[m
[32m+[m[32m                    meeting_date,[m
[32m+[m[32m                    race_id,[m
[32m+[m[32m                    race_number,[m
[32m+[m[32m                    runner_id,[m
[32m+[m[32m                    tab_number,[m
[32m+[m[32m                    updated_at,[m
[32m+[m[32m                    created_at,[m
[32m+[m[32m                    {horse_expr} AS horse,[m
[32m+[m[32m                    {trainer_expr} AS trainer,[m
[32m+[m[32m                    actual_position,[m
[32m+[m[32m                    final_score,[m
[32m+[m[32m                    confidence,[m
[32m+[m[32m                    ROW_NUMBER() OVER ([m
[32m+[m[32m                        PARTITION BY[m
[32m+[m[32m                            meeting_id,[m
[32m+[m[32m                            COALESCE(race_id::TEXT, race_number::TEXT, ''),[m
[32m+[m[32m                            CASE[m
[32m+[m[32m                                WHEN runner_id IS NOT NULL AND runner_id > 0[m
[32m+[m[32m                                    THEN 'ID:' || runner_id::TEXT[m
[32m+[m[32m                                ELSE 'NAME:' || UPPER(TRIM(COALESCE([m
[32m+[m[32m                                    {horse_expr},[m
[32m+[m[32m                                    ''[m
[32m+[m[32m                                ))) || '|TAB:' || COALESCE(tab_number::TEXT, '')[m
[32m+[m[32m                            END[m
[32m+[m[32m                        ORDER BY[m
[32m+[m[32m                            updated_at DESC NULLS LAST,[m
[32m+[m[32m                            created_at DESC NULLS LAST,[m
[32m+[m[32m                            id DESC[m
[32m+[m[32m                    ) AS start_snapshot_rank[m
[32m+[m[32m                FROM rrt_runner_factor_snapshots[m
[32m+[m[32m                WHERE actual_position IS NOT NULL[m
[32m+[m[32m                  AND {horse_expr} IS NOT NULL[m
[32m+[m[32m                  AND UPPER({horse_expr}) NOT IN ('N/A', 'UNKNOWN', 'NONE')[m
[32m+[m[32m            ),[m
[32m+[m[32m            distinct_starts AS ([m
[32m+[m[32m                SELECT[m
[32m+[m[32m                    meeting_id,[m
[32m+[m[32m                    meeting_date,[m
[32m+[m[32m                    race_id,[m
[32m+[m[32m                    race_number,[m
[32m+[m[32m                    runner_id,[m
[32m+[m[32m                    tab_number,[m
[32m+[m[32m                    horse,[m
[32m+[m[32m                    trainer,[m
[32m+[m[32m                    actual_position,[m
[32m+[m[32m                    final_score,[m
[32m+[m[32m                    confidence,[m
[32m+[m[32m                    updated_at,[m
[32m+[m[32m                    created_at[m
[32m+[m[32m                FROM completed_rows[m
[32m+[m[32m                WHERE start_snapshot_rank = 1[m
[32m+[m[32m            ),[m
[32m+[m[32m            horse_rollup AS ([m
[32m+[m[32m                SELECT[m
[32m+[m[32m                    COALESCE([m
[32m+[m[32m                        CASE[m
[32m+[m[32m                            WHEN runner_id IS NOT NULL AND runner_id > 0[m
[32m+[m[32m                                THEN 'ID:' || runner_id::TEXT[m
[32m+[m[32m                            ELSE NULL[m
[32m+[m[32m                        END,[m
[32m+[m[32m                        'NAME:' || UPPER(TRIM(horse))[m
[32m+[m[32m                    ) AS horse_key,[m
[32m+[m[32m                    MAX(horse) AS horse,[m
[32m+[m[32m                    COUNT(*) AS runner_count,[m
[32m+[m[32m                    SUM(CASE WHEN actual_position = 1 THEN 1 ELSE 0 END) AS win_count,[m
[32m+[m[32m                    SUM(CASE WHEN actual_position BETWEEN 1 AND 3 THEN 1 ELSE 0 END) AS place_count,[m
[32m+[m[32m                    ROUND([m
[32m+[m[32m                        (SUM(CASE WHEN actual_position = 1 THEN 1 ELSE 0 END)::NUMERIC[m
[32m+[m[32m                        / NULLIF(COUNT(*), 0)) * 100,[m
[32m+[m[32m                        2[m
[32m+[m[32m                    ) AS win_strike_rate,[m
[32m+[m[32m                    ROUND([m
[32m+[m[32m                        (SUM(CASE WHEN actual_position BETWEEN 1 AND 3 THEN 1 ELSE 0 END)::NUMERIC[m
[32m+[m[32m                        / NULLIF(COUNT(*), 0)) * 100,[m
[32m+[m[32m                        2[m
[32m+[m[32m                    ) AS place_strike_rate,[m
[32m+[m[32m                    ROUND(AVG(final_score), 2) AS avg_final_score,[m
[32m+[m[32m                    ROUND(AVG(confidence), 2) AS avg_confidence[m
[32m+[m[32m                FROM distinct_starts[m
[32m+[m[32m                GROUP BY[m
[32m+[m[32m                    COALESCE([m
[32m+[m[32m                        CASE[m
[32m+[m[32m                            WHEN runner_id IS NOT NULL AND runner_id > 0[m
[32m+[m[32m                                THEN 'ID:' || runner_id::TEXT[m
[32m+[m[32m                            ELSE NULL[m
[32m+[m[32m                        END,[m
[32m+[m[32m                        'NAME:' || UPPER(TRIM(horse))[m
[32m+[m[32m                    )[m
[32m+[m[32m                HAVING COUNT(*) >= %s[m
[32m+[m[32m            ),[m
[32m+[m[32m            latest_trainer AS ([m
[32m+[m[32m                SELECT DISTINCT ON ([m
[32m+[m[32m                    COALESCE([m
[32m+[m[32m                        CASE[m
[32m+[m[32m                            WHEN runner_id IS NOT NULL AND runner_id > 0[m
[32m+[m[32m                                THEN 'ID:' || runner_id::TEXT[m
[32m+[m[32m                            ELSE NULL[m
[32m+[m[32m                        END,[m
[32m+[m[32m                        'NAME:' || UPPER(TRIM(horse))[m
[32m+[m[32m                    )[m
[32m+[m[32m                )[m
[32m+[m[32m                    COALESCE([m
[32m+[m[32m                        CASE[m
[32m+[m[32m                            WHEN runner_id IS NOT NULL AND runner_id > 0[m
[32m+[m[32m                                THEN 'ID:' || runner_id::TEXT[m
[32m+[m[32m                            ELSE NULL[m
[32m+[m[32m                        END,[m
[32m+[m[32m                        'NAME:' || UPPER(TRIM(horse))[m
[32m+[m[32m                    ) AS horse_key,[m
[32m+[m[32m                    trainer[m
[32m+[m[32m                FROM distinct_starts[m
[32m+[m[32m                WHERE trainer IS NOT NULL[m
[32m+[m[32m                  AND UPPER(trainer) NOT IN ('N/A', 'UNKNOWN', 'NONE')[m
[32m+[m[32m                ORDER BY[m
[32m+[m[32m                    COALESCE([m
[32m+[m[32m                        CASE[m
[32m+[m[32m                            WHEN runner_id IS NOT NULL AND runner_id > 0[m
[32m+[m[32m                                THEN 'ID:' || runner_id::TEXT[m
[32m+[m[32m                            ELSE NULL[m
[32m+[m[32m                        END,[m
[32m+[m[32m                        'NAME:' || UPPER(TRIM(horse))[m
[32m+[m[32m                    ),[m
[32m+[m[32m                    meeting_date DESC NULLS LAST,[m
[32m+[m[32m                    updated_at DESC NULLS LAST,[m
[32m+[m[32m                    created_at DESC NULLS LAST[m
[32m+[m[32m            )[m
[32m+[m[32m            SELECT[m
[32m+[m[32m                hr.horse,[m
[32m+[m[32m                COALESCE(lt.trainer, 'Not recorded') AS trainer,[m
[32m+[m[32m                hr.runner_count,[m
[32m+[m[32m                hr.win_count,[m
[32m+[m[32m                hr.place_count,[m
[32m+[m[32m                hr.win_strike_rate,[m
[32m+[m[32m                hr.place_strike_rate,[m
[32m+[m[32m                hr.avg_final_score,[m
[32m+[m[32m                hr.avg_confidence[m
[32m+[m[32m            FROM horse_rollup hr[m
[32m+[m[32m            LEFT JOIN latest_trainer lt[m
[32m+[m[32m              ON lt.horse_key = hr.horse_key[m
[32m+[m[32m            ORDER BY[m
[32m+[m[32m                hr.place_strike_rate DESC,[m
[32m+[m[32m                hr.win_strike_rate DESC,[m
[32m+[m[32m                hr.place_count DESC,[m
[32m+[m[32m                hr.win_count DESC,[m
[32m+[m[32m                hr.runner_count DESC,[m
[32m+[m[32m                hr.avg_final_score DESC,[m
[32m+[m[32m                hr.horse ASC[m
[32m+[m[32m            LIMIT %s;[m
[32m+[m[32m            """,[m
[32m+[m[32m            (MIN_HORSE_RUNS, HISTORICAL_HORSE_LIMIT),[m
[32m+[m[32m        )[m
         for horse in horses:[m
             horse["evidence_status"] = "Established" if _to_int(horse.get("runner_count")) >= 5 else "Emerging"[m
 [m
[36m@@ -1195,8 +1354,8 @@[m [mdef get_each_way_leaderboards([m
             },[m
             "limit": limit,[m
             "historical_horse_limit": HISTORICAL_HORSE_LIMIT,[m
[31m-            "ranking_method": "All completed runner-factor rows; ranked by place strike rate, then win strike rate and sample size after minimum sample thresholds.",[m
[31m-            "horse_ranking_note": "This is an aggregated historical horse leaderboard across completed runs. It is separate from the per-meeting Top 20 prediction ranking.",[m
[32m+[m[32m            "ranking_method": "Trainer, jockey and combination leaderboards use completed runner-factor rows. Historical horses are deduplicated to one row per actual start before win/place rates are calculated.",[m
[32m+[m[32m            "horse_ranking_note": "This is an aggregated historical horse leaderboard across distinct actual starts. Repeated model-version snapshots for the same meeting, race and runner are counted once. It is separate from the per-meeting Top 20 prediction ranking.",[m
             "dataset": totals,[m
             "top_trainers": _rank_rows(trainers),[m
             "top_jockeys": _rank_rows(jockeys),[m
[36m@@ -1376,8 +1535,8 @@[m [mdef generate_learning_report_html() -> str:[m
         '<h3>Top 10 Jockeys</h3>', _html_table(['Rank','Jockey','Runs','Wins','Places','Win %','Place %','Avg Score','Avg Confidence'], [[i.get('rank'),i.get('jockey'),i.get('runner_count'),i.get('win_count'),i.get('place_count'),_pct(i.get('win_strike_rate')),_pct(i.get('place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in ((report.get('each_way_leaderboards') or {}).get('top_jockeys') or [])[:10]]),[m
         '<h3>Top 10 Trainer / Jockey Combinations</h3>', _html_table(['Rank','Combination','Runs','Wins','Places','Win %','Place %','Avg Score','Avg Confidence'], [[i.get('rank'),i.get('trainer_jockey_combination'),i.get('runner_count'),i.get('win_count'),i.get('place_count'),_pct(i.get('win_strike_rate')),_pct(i.get('place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in ((report.get('each_way_leaderboards') or {}).get('top_trainer_jockey_combinations') or [])[:10]]),[m
         '<h3>Top 20 Historical Horse Performance</h3>',[m
[31m-        '<div class="note">Aggregated historical performance across completed runner-factor records. This table is separate from the per-meeting Top 20 prediction ranking. Emerging = 2-4 completed runs; Established = 5 or more completed runs.</div>',[m
[31m-        (_html_table(['Rank','Horse','Status','Runs','Wins','Places','Win %','Place %','Avg Score','Avg Confidence'], [[i.get('rank'),i.get('horse'),i.get('evidence_status'),i.get('runner_count'),i.get('win_count'),i.get('place_count'),_pct(i.get('win_strike_rate')),_pct(i.get('place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in ((report.get('each_way_leaderboards') or {}).get('top_horses') or [])[:20]]) if ((report.get('each_way_leaderboards') or {}).get('top_horses') or []) else '<div class="note">Insufficient historical horse performance data available. A minimum of two completed runs is required before inclusion.</div>'),[m
[32m+[m[32m        '<div class="note">Aggregated historical performance across distinct actual race starts. Repeated model-version snapshots for the same horse and race are counted once. The Trainer shown is from the latest completed recorded start. This table is separate from the per-meeting Top 20 prediction ranking. Emerging = 2-4 completed runs; Established = 5 or more completed runs.</div>',[m
[32m+[m[32m        (_html_table(['Rank','Horse','Trainer','Status','Runs','Wins','Places','Win %','Place %','Avg Score','Avg Confidence'], [[i.get('rank'),i.get('horse'),i.get('trainer'),i.get('evidence_status'),i.get('runner_count'),i.get('win_count'),i.get('place_count'),_pct(i.get('win_strike_rate')),_pct(i.get('place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in ((report.get('each_way_leaderboards') or {}).get('top_horses') or [])[:20]]) if ((report.get('each_way_leaderboards') or {}).get('top_horses') or []) else '<div class="note">Insufficient historical horse performance data available. A minimum of two distinct completed starts is required before inclusion.</div>'),[m
         '<h2>Evidence-Based Factor Analysis</h2>',[m
         '<div class="note">This section compares completed runner factor scores against actual results. It reports against the active v2.20.1 production weights. Automatic weight changes are disabled, and all future proposals remain inactive until manually reviewed and approved.</div>',[m
         '<h3>Factor Effectiveness Ranking</h3>',[m
[36m@@ -1484,11 +1643,15 @@[m [mdef generate_learning_report_pdf_bytes() -> bytes:[m
     story.append(Paragraph("Top 10 Trainer / Jockey Combinations", styles["RRTHeading"]))[m
     story.append(t(["Rank","Combination","Runs","Wins","Places","Win %","Place %","Avg Score","Avg Conf"], [[i.get('rank'),i.get('trainer_jockey_combination'),i.get('runner_count'),i.get('win_count'),i.get('place_count'),_pct(i.get('win_strike_rate')),_pct(i.get('place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in (leaderboards.get('top_trainer_jockey_combinations') or [])[:10]]))[m
     story.append(Paragraph("Top 20 Historical Horse Performance", styles["RRTHeading"]))[m
[31m-    story.append(Paragraph("Aggregated historical performance across completed runner-factor records. This table is separate from the per-meeting Top 20 prediction ranking. Emerging = 2-4 completed runs; Established = 5 or more completed runs.", styles["BodyText"]))[m
[32m+[m[32m    story.append(Paragraph("Aggregated historical performance across distinct actual race starts. Repeated model-version snapshots for the same horse and race are counted once. The Trainer shown is from the latest completed recorded start. This table is separate from the per-meeting Top 20 prediction ranking. Emerging = 2-4 completed runs; Established = 5 or more completed runs.", styles["BodyText"]))[m
     if leaderboards.get('top_horses'):[m
[31m-        story.append(t(["Rank","Horse","Status","Runs","Wins","Places","Win %","Place %","Avg Score","Avg Conf"], [[i.get('rank'),i.get('horse'),i.get('evidence_status'),i.get('runner_count'),i.get('win_count'),i.get('place_count'),_pct(i.get('win_strike_rate')),_pct(i.get('place_strike_rate')),i.ge