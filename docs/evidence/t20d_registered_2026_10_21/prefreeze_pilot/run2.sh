source /usr/lib/openfoam/openfoam2512/etc/bashrc || true
cd /w/$1
dt=$2; nout=$3; n=$4
sed -i -e "s/^adjustTimeStep .*/adjustTimeStep no;/" -e "s/^deltaT .*/deltaT $dt;/" -e "s/^endTime .*/endTime $(python3 -c "print($dt*$n)");/" -e "s/^writeInterval .*/writeInterval 100;/" system/controlDict
sed -i -e "s/nOuterCorrectors .*/nOuterCorrectors $nout;/" system/fvSolution
rm -rf [1-9]* 0.* 2>/dev/null
s=$(date +%s.%N); pimpleFoam > log.pimple_${dt}_${nout} 2>&1; echo "rc=$?"; e=$(date +%s.%N)
echo "wall_s $(echo "$e - $s" | bc) steps $(grep -c '^Time = ' log.pimple_${dt}_${nout})"
grep "^Courant" log.pimple_${dt}_${nout} | awk '{print $6}' | sort -g | tail -1
grep "Solving for p" log.pimple_${dt}_${nout} | tail -2
grep "^ExecutionTime" log.pimple_${dt}_${nout} | tail -1
