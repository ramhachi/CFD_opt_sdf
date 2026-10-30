
source /usr/lib/openfoam/openfoam2512/etc/bashrc || true
cd /w/$1
gmshToFoam mesh.msh > log.gmshToFoam 2>&1
python3 - <<'PY'
import re
from pathlib import Path
b = Path("constant/polyMesh/boundary"); t = b.read_text()
for name, typ in (("front","empty"),("back","empty"),("airfoil","wall"),("ground","wall")):
    t, n = re.subn(rf"(\b{name}\s*\{{[^{{}}]*?)type\s+\w+\s*;", rf"\g<1>type {typ};", t, count=1); assert n == 1
b.write_text(t)
PY
s=$(date +%s.%N); simpleFoam > log.simpleFoam 2>&1; e=$(date +%s.%N)
echo "simple_s $(echo "$e - $s" | bc)"
rm -rf 0 && mv 400 0 && rm -f 0/uniform/time 2>/dev/null || true
cp pimple/* system/
s=$(date +%s.%N); timeout ${2:-900} pimpleFoam > log.pimpleFoam 2>&1 || echo "pimple rc=$?"; e=$(date +%s.%N)
echo "pimple_s $(echo "$e - $s" | bc)"
grep -c "^Time = " log.pimpleFoam
grep "^Courant" log.pimpleFoam | tail -3
grep "^deltaT" log.pimpleFoam | tail -2
grep "^ExecutionTime" log.pimpleFoam | tail -1
tail -5 log.pimpleFoam
