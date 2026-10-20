#!/bin/bash
# LOCAL-OF-01 registered runs (docs/local_openfoam_env_gate_2026_10_20.md section 4). Usage: run_gate.sh PHASE [NAME]
#   t20c | t20b | x3u3 | sanitise | compare | extra NAME (t20b_c, t20b_d) | repeat RUN (a second attempt of RUN, section 6)
set -u
cd "$(dirname "$0")/../.."
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
PY=/Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python
L=work/local_openfoam; K=$L/kernels; D=$L/datasets; R=$L/runs; mkdir -p $R
T20B_IDS="sa-wf_h0.224_fine30_da-1 sa-wf_h0.224_fine30_da+1 sa-wf_h0.134_med30_da-0.25 sa-wf_h0.134_med30_da+0.25 sa-wf_h0.09_fine30_da+1"
X3_IDS=$(for k in 17p 17m; do for s in baseline D0_interface_offset_minus D0_interface_offset_plus D1_filtered_seed11_minus D1_filtered_seed11_plus D2_filtered_seed2026_minus D2_filtered_seed2026_plus; do printf 'frm_%s_%s ' $s $k; done; done)
X3=infra/kaggle/kernel_openfoam_xfid_gridphase_x3_formal
NOTES="/Users/sota/Library/Application Support/Claude/side-session-notes/local_14b906be-5e2f-4d41-bbed-a96954c75dfa"
load() { echo "$(date -u +%FT%TZ) $1 load=$(sysctl -n vm.loadavg) swap=$(sysctl -n vm.swapusage | cut -c1-60)"; }
one() {  # one registered run by name
  case "$1" in
    t20c_smoke2_*) python3 scripts/local_openfoam.py run $K/t20c_smoke2 --out $R/$2 ;;
    t20b_*) python3 scripts/local_openfoam.py run $K/t20b_wf/runner.py --out $R/$2 --subset t20b $T20B_IDS ;;
    x3_*) python3 scripts/local_openfoam.py run $X3/runner.py --out $R/$2 --dataset $D/x3_formal --cpus 1 --subset x3 $X3_IDS ;;
    u3_smoke_*) python3 scripts/local_openfoam.py run $K/u3_smoke --out $R/$2 --dataset $D/u3_smoke --cpus 1 ;;
  esac; echo "$2 rc=$?"
}
case "$1" in
  t20c) for n in a b; do load start_$n; one t20c_smoke2_$n t20c_smoke2_$n; done; load end ;;
  t20b) for n in a b; do load start_$n; one t20b_$n t20b_$n; done; load end ;;
  extra) load start_$2; one $2 $2; load end ;;
  repeat) load start_$2; one $2 $2.attempt2; load end ;;
  x3u3) load start
    one x3_a x3_a & one x3_b x3_b & one u3_smoke_a u3_smoke_a & one u3_smoke_b u3_smoke_b & wait; load end ;;
  sanitise)  # the frozen M2 sanitiser (unc01_u3_prepare.py at a646e918); the raw run stays under work/ and is read only by the comparator's U4
    S=$2; $PY "$3/scripts/unc01_u3_prepare.py" strip-smoke $R/$S/openfoam_xfid_gridphase_x3 $R/${S}_sanitized/openfoam_xfid_gridphase_x3 >/dev/null && cp $R/$S/local_run.json $R/${S}_sanitized/ && echo sanitised ;;
  compare) $PY scripts/local_openfoam_gate.py --runs $R --u3-kaggle $L/reference/docs/evidence/unc01_2026_10_20/u3/smoke/output \
             --u3-kaggle-raw "$NOTES/unc01_u3_kaggle_smoke_raw" --out docs/evidence/local_openfoam_env_2026_10_20/gate_result.json ;;
esac
