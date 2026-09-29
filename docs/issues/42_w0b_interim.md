# Issue #42 前半 (W0b-Kaggle) 中間報告

状態: 作業中断 (指示により停止)。事実のみ。

## Kaggle 提出状況

- Kaggle への kernel / dataset の submit は一切行っていない。実行中のジョブも無い。
- 実施した Kaggle 操作は読み取りのみ: `kaggle kernels list --mine`, `kaggle datasets list --mine`, `kaggle --version` (2.2.4), `kaggle kernels push --help`。

## 完了したこと (調査)

- 既存パターンの調査: `scripts/t4_backend_identity.py`, `scripts/register_sdf_native_w0b_t4_cuda_env_2026_09.py`, `scripts/w0b_t4_smoke.jl`, 旧 Colab W0b criteria/証跡, `infra/kaggle/kernel_w2b`, `kernel_w3_cuda_diagnostic`, `kernel_w3_owner_type_probe`, `scripts/register_kaggle_w3_owner_type_probe_2026_09.py`, `scripts/verify_kaggle_k0.py`, `scripts/verify_kaggle_w1g.py`。
- 重要な発見 (issue #42 の前提とずれる点):
  - Kaggle T4 上の W1g round 2 は既に PASS 済み (`docs/evidence/kaggle_w1g_round2_result_2026_09.json`, kernel `ramhachi888/cfd-opt-sdf-k0` version 4)。K0 (`kaggle_k0_result_2026_09.json`)、W2-T4b、W2b、W3、W4、FD v16 も Kaggle T4 で実行済み。issue #42 の「Kaggle 版 W0b/W1g を新規登録」は一部が既に事実上存在する。W1g を再登録すべきかは要判断 (本作業では W1g は対象外)。
  - Kaggle の観測値は全 round で一貫: 2x Tesla T4、nvidia-smi driver 580.159.04、VRAM 15360 MiB、compute capability 7.5.0、CUDA driver API 13.3.0、CUDA runtime 12.8.0、Julia 1.12.6、CUDA.jl 6.3.1、WaterLily 1.8.0。K0/W1g/W2-T4b の criteria が `cuda_runtime_version` を 13.3.0 と書いているのは、driver API 値の取り違えで、W2b round 3 以降で 12.8.0 (runtime) / 13.3.0 (driver API) に訂正されている。
  - `kaggle_k0_result` の UUID は run ごとに異なる (K0: `GPU-09c4b446...`/`GPU-d0099633...`, W1g: `GPU-425a09be...`/`GPU-cbae5346...`)。UUID は登録束縛できず、実測記録のみが妥当。
- `CUDA.uuid(CUDA.device())` が `CUDA` モジュールで解決できることを macOS の temp 環境 (CUDA.jl 最新) で確認 (`isdefined(CUDA,:uuid)` と `isdefined(CUDACore,:uuid)` が共に true)。GPU 実機では未確認。

## 設計した identity 方針 (ドラフト)

- 束縛する項目: GPU 型式 Tesla T4、compute capability 7.5.0、VRAM 15360 MiB、driver は `580\.\d+\.\d+` (major を束縛し、厳密値は記録)、CUDA driver API 13.3.0、CUDA runtime 12.8.0、Julia 1.12.6、CUDA.jl 6.3.1、WaterLily 1.8.0、T4 Project/Manifest SHA-256、Julia アーカイブ SHA-256。
- UUID は束縛しない。理由: Kaggle は run ごとに物理 GPU が変わる。nvidia-smi index 0 の UUID を記録し、形式・inventory 内での一意性・Julia の `CUDA.uuid` との一致のみ検査する。
- ゲート案: G0 (T4/VRAM/driver 型式)、G1-G5 (旧 Colab W0b の CUDA functional / CuArray / KernelAbstractions / WaterLily CUDA ext / no solver step を意味そのまま移植)、G6 identity、G7 UUID 記録の整合、G8 source binding、G9 artifact 完全性。
- 実行形態案: dataset 無し、private script kernel `ramhachi888/cfd-opt-sdf-w0b-kaggle-t4-identity` (既存 slug と非衝突を `kernels list --mine` / `datasets list --mine` で確認済み)。runner は criteria を含む commit を GitHub から pin fetch し、SHA-256 を検証してから既存 `scripts/w0b_t4_smoke.jl` を実行。runner 自身は criteria commit を埋め込むため criteria の source_files には含めず、runner SHA-256 を fingerprint に記録して host verifier が commit 済みファイルと照合する。

## ファイルの状態 (すべて未検証 WIP、コミットのみ)

- 変更: `scripts/t4_backend_identity.py` に `verify_kaggle_backend_identity()` を追記 (既存関数は無変更)。
- 新規: `scripts/register_kaggle_w0b_t4_identity_2026_09.py` (criteria registrar)、`scripts/verify_kaggle_w0b.py` (host verifier、`--record --attempt N` 付き)、`infra/kaggle/kernel_w0b/runner.py` (`CRITERIA_COMMIT` / `CRITERIA_SHA256` は `TO_BE_PINNED` のまま)、`infra/kaggle/kernel_w0b/kernel-metadata.json`。
- いずれもテスト・実行・compileall を未実施。文法エラーの有無も未確認。

## 未実施

- criteria は未登録 (`docs/evidence/kaggle_w0b_t4_identity_criteria_2026_09.json` は存在しない)。したがって「結果を見る前に登録」の手順の途中で止まっている。
- `tests/test_w0b_kaggle_registration.py` 未作成。registrar が source_files に含めるため、登録前に最終化が必要 (登録後に verifier/registrar/tests を編集すると G8 が崩れ、新 round が必要になる)。
- runner の pin、Kaggle 実行、host 検証、result JSON、`docs/issues/42_w0b_result.md`、関連 pytest、全体 pytest はいずれも未実施。
- W1g は指示どおり未着手。

## 未検証事項

- `CUDA.uuid` が CUDA.jl 6.3.1 (Manifest 固定版) で使えるか。
- Kaggle kernel が feature ブランチ (`refs/heads/feat/issue-42-w0b-kaggle`) を匿名 fetch できるか (既存 runner は `codex/kaggle-batch-migration` を同方式で fetch している)。
- verifier の G8 (`git show <criteria_commit>:path`) の挙動。

## 推奨する次の手順

1. 上記 WIP をレビューし、`tests/test_w0b_kaggle_registration.py` を書く (合成 fixture で evaluate の各ゲート、drift/別 GPU/UUID 不整合の fail-closed、tmp git repo での G8 を検証)。関連テストと compileall を通す。
2. clean HEAD で registrar を実行し criteria + sidecar をコミット、push。
3. runner に `CRITERIA_COMMIT` / `CRITERIA_SHA256` を pin してコミット、push。
4. `kaggle kernels push -p infra/kaggle/kernel_w0b --accelerator NvidiaTeslaT4 --timeout 1800` を 1 回だけ実行し、`kernels output <ref>/<version>` を取得して `verify_kaggle_w0b.py --record` で記録。
5. #42 の W1g 部分は、Kaggle W1g round 2 PASS が既存である点を踏まえ、#36 診断後に再登録が必要か判断する。
