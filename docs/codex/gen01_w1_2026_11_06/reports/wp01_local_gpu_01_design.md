# WP1：LOCAL-GPU-01 設計メモ（Amendment 3）

2026-11-06。開始 HEAD は PR #88 の `e6c57e7b`、登録済み tool の基準は `e3dcdf6188df6079e197eb28f7fcba1451ec512d`。ユーザーの Amendment 3 と、review worktree の LOCAL-GPU-01 §11 Amendment 2 を優先する。道具・合成テスト・短い CPU 検証のみを行い、実機 GPU、Kaggle、登録、凍結、roadmap 改定は行わない。

## 読んだ契約と保全

`00_README.md`、AGENTS、docs README / STATE / branching / GEN-01 plan、LOCAL-GPU-01 rev0 と review worktree の amendment、LOCAL-OF-01 §§2–7 とその runtime/comparator/infra/tests、harness schema/build/verify/template/README、HARNESS-01 campaign と最小 rendered kernel、facts 全文を確認。phase_plan は worker の非重複三分割で全文を確認。handoff / problem_register / problem_resolution は Amendment 1 指定の目次・該当する GPU / Kaggle / harness / evidence 節を確認した。

判断の根拠：`docs/phase_plan.md` が status / execution order の唯一の authority、problem_register は issue ledger。PROC-01 に従い契約・能力の証拠を対象物理・benchmark の資格に昇格させない。既存 evidence / campaign / freeze / rendered kernel / 登録 job / 保護テスト / conftest / Project / Manifest / `julia/CFDSDFWaterLily/src/` の bytes を保全する。

前回の「T4 契約は byte 不変」は誤りだった。schema は BASE_PIN、schema/build/verify は TOOL_FILES でもあり、編集により UNC-01 smoke の再検証と登録 tool SHA を壊していた。3 ファイルを `git show e3dcdf61:<path>` から作業ファイルへ復元し、index は変更しない。これはユーザー指定の checkout と同じ内容の復元を sandbox 内で行う方法である。今回の回帰テストは historical archive だけではなく、**現在の tree** で UNC-01 U01 smoke と formal を再検証して保存済み table と byte 比較する。

## backend / render / verify

新規 `backend_profiles.py` だけに profile selector、local validation、renderer、verifier wrapper を置く。既定 `kaggle_t4` は登録 tool / template / grid01 selector をそのまま使う。UUID fallback は LOCAL のみに限定する。

派生 campaign の top-level `pins` に backend module 自身を入れる。checkpoint job を選ぶ kernel は `gen01/Checkpoint.jl` を明示 pin する。元の first-state T4 byte gate は local campaign から除き、同一機 C1 後に local reference を gate に記録する。元 campaign は不変。

local render は unchanged `campaign_build.pin_block` / `pins` を利用する。runner 内で pinned checkout の明示パスから backend module を読み、`backend_profile` を除いた campaign を unchanged `SC.validate_campaign` へ渡す。RTX 4070 Ti の物理 index0、可能なら NVML UUID、必須 CUDA UUID、probe.logical_device_count=1 を確認する。runner の used_gpu_count=1 は bookkeeping であり、singleton の実証は probe にある。local verifier は unchanged harness の整合性・schema・窓・pin 検査を local selector/probe/gpu_name で wrap する。process-global の登録 verifier を書き換えない。

出力は方式(a)：既存 `CAMPAIGN_WORK_ROOT`。登録 harness は dataset を使わず `/kaggle` 全体の bind は不要。将来 dataset が必要な runner にだけ既存 read-only bind helper を使う。実行時の rendered runner は変更しない。

## lock / run / bench

GPU project は登録済み `julia/CFDSDFWaterLilyT4`（WaterLily1.8.0 / CUDA6.3.1）、CPU checkpoint は `julia/CFDSDFWaterLily`。両 Manifest は変更しない。

canonical JSON は UTF-8、sort_keys、indent2、末尾 LF 一つ、nonfinite 拒否。sidecar は日時も含む全 lock bytes の SHA。欠測は null でなく理由付き error。GPU 名 / driver / Julia executable SHA / Manifest SHA が必須。加えて Julia install root を `campaign_schema.sha256_path` で測り、専用 JULIA_DEPOT_PATH と Manifest-resolved package tree を bind する。tarball pin は期待値と観測値を区別し、未取得 archive を検証済みと書かない。Windows HAGS は読めるときに記録する。

`check-lock` は sidecar/canonical bytes と再取得 environment を照合する。自由 VRAM や日時を identity にしない。`run` は新規 out、CUDA_VISIBLE_DEVICES=0 / CUDA_DEVICE_ORDER=PCI_BUS_ID / JULIA_NUM_THREADS=1 を要求し、実際に子へ渡す JULIA_* / CUDA_* / NVIDIA_* / WSL* snapshot を local_run に記録する。lock と runner の Project/Manifest pins を実行前後に確認する。各段の process envelope の壁時計、10秒間隔の peak VRAM、exit / DONE / 全出力 SHA を保存する。

watch は60秒 cadenceでclock/temperature/power/memory/utilization/UUIDとreset観測を記録する。unsupportedなoptional値とquery全体の失敗を区別し、欠測をresetなしや正常値で埋めない。R5は中断runとcheckpointを新規resume_inputへcopyしSHAとjob restore eventを結ぶ。R0 benchもlock SHAとVRAMを記録する。TGVは128³ Float32/Re1600の固定した**custom fixture**であり、WaterLily benchmark suiteそのものではない。native Windowsは比較benchのみでharness移植ではない。

## gate / C1–C6

C1は同一campaign/source/runner/environment、geometry/placement/scaling/stepを要求し、force CSV byte一致ならBITWISE、全sampleの最大相対差≤1e-6ならTOLERANCE。相対差の式はabs(a-b)/max(abs(a),abs(b),1e-300)でspecどおり。near-zero列のabsolute floorは勝手に導入しない。

C2は両R2へlocal verify wrapperをsubprocessで呼び、unchanged harnessの検査を再利用する。C3はmanifest/table/SHA256SUMSから参照SHAを読み、T4窓平均と全sampleの最大相対差、UNC phase SDを記述する。C4のT4錨はliteral5.5e7/5.6e7をやめ、C3参照summaryのcells×steps/solver wallから導出してsummary SHAを残す。登録jobのstepsは初回warmupを含むので、(steps−1)のtimed estimateも別記する。

C5はR3/R5の同一identity、kill→checkpoint→restore provenanceとendpoint-clipped time-weighted窓統計をC1の級で比較する。C6のclockはutilization≥50% **または**明示的に記録されたsolver interval内のsampleのみでdrawdown<15%。本wrapperはRUN段のprocess envelopeしか計れずJITを除いたintervalを推定しないため、通常はutilization条件を用いる。VRAMは各active intervalの最初60秒を除いたrange≤device totalの5%、repeat peak間の相対変動≤2%（local_runの全10秒sampleのpeak、startupも含む。分母は最大peak）を要求する。optional clock/temp/power欠測、required memory/utilization/UUID欠測はINCOMPLETE。非有限値やresetはFAIL。90秒gap/60秒first-sample allowanceはdevelopment defaultsとしてgateに記録する。

PASS条件はC1∈{BITWISE,TOLERANCE}かつC2/C5/C6 PASSだけ。C3/C4のFAIL/INCOMPLETEは別に報告し判定を妨げない。R1–R6で観測されたCUDA UUIDは一つに拘束する。R4欠測は記述に残し、取得されたR4のUUID矛盾をthroughput差と混同しない。DONEなのにidentity fileがない場合はFAIL。gateはtempへ完全書込後にexclusive hardlinkでpublishし、計算中の例外で空のgate.jsonを予約しない。既存出力は計算前に拒否する。

## WP4 checkpoint API

登録directory pinの`src/`には追加も編集もしない。新規モジュールは`julia/CFDSDFWaterLily/gen01/Checkpoint.jl`。scripts内jobから既存main moduleをinclude後、次で読む。

```julia
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "gen01", "Checkpoint.jl"))
using .CFDSDFWaterLily.Checkpoint
save_checkpoint(path, sim, step, rows; identity=study_geometry_sampling_sha)
payload = load_checkpoint(path)
restore_checkpoint!(fresh_sim, payload; identity=study_geometry_sampling_sha)
# payload.step+1 と copy(payload.rows) から続ける
```

save→path、load→validated NamedTuple、restore→fresh_sim。identityは必須の非空文字列で、restoreが自身で照合してからfieldを変更する。stepは個々のmom_step!の完了回数、length(Δt)==step+1。`sim_step!(sim,t_end)`は一度に複数advanceをするので呼出回数をstepにしてはいけない。

u/p/u⁰/全Δt/時刻/step/force rows/runtime config/caller identityを保存。RNG/body closure/device pointerは保存しない。両ManifestのJLD2はweakdep宣言のみで実依存がなくSerializationを使用。信頼した自作file、標準Flow/MultiLevelPoisson、同一body/config、default remeasure=trueに限る。copy jobは登録flow32 jobへのcheckpoint hookのみ、force writer/窓/位相/単位は保持し、正確なdiffを別fileにする。

## 検証 / 引き継ぎ

合成データでlock/canonicalSHA/mismatch、stub DONE/run record、identity、C1–C6、idle除外/VRAM leak/telemetry欠測、one-shot拒否/例外後再試行、include closure、current-tree登録table再検証を確認する。CPU64×32/100step/50step保存再開と小格子benchを実行する。全体pytestはAmendment3の結果側だけをMetal除外の指定引数で完走し、前回の完走baseの失敗集合[]と比較する。前回baseのログを記録SHAで検証してreportsへ保全、今回のfocus/full/JUnit/CPU出力も一時パスでなくreportsへ保存する。compileall、diff --check、保護scope bytesも確認する。

OpenCode Go MCPなし、CLIモデル確認も既定logのFileSystem.openで起動失敗。global設定/課金を変更せずnative workerをbackend、gate、runtime identityに非重複分担。親はcheckpoint/文書/統合と最終検証を担当。Amendment3によりgit add/commit/pushは行わず、同じworktreeからhost Claudeがcommit/push/PR更新する。報告に変更/新規/復元の完全なfile listを載せる。attempt1の3記録は保全する。

## WSL2でだけ分かる未確認事項

Windows build/driver/WSL kernel/distro、HAGS可視性、設定反映、Julia起動/JIT/小kernel launch遅延、CUDA.functional、NVMLのclock/power/temp/utilization/VRAM/UUID取得、Display TDR event4101可視性、optional bind要否/権限/解除、専用depotの初回instantiateとlock後安定性、GPU別process checkpoint再開、native Windows比、6時間loopの温度/clock/RAM/VRAMは未確認。KB5127936保留は提示資料の回帰回避注意であり、本実装が当該障害を独自検証した主張ではない。実装DONEとLOCAL-GPU-01 PASSは別で、物理/格子独立/高Re/FSAE資格は与えない。
