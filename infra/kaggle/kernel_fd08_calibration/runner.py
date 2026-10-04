#!/usr/bin/env python3
"""Run the preregistered FD-08 calibration as one Kaggle script."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import runpy
import tempfile
import zlib


_CORE_SOURCE_B85 = (
    "c-p-^YjfK;lHc_!INZ8gG9$^4IGKz#nktViPrU2cE<a{wPp3ms5+!j=ksOlpBQF2<>jyvrBqb}^-E&oJk^s6JjqXOH(Lnz4-OegY"
    "cg8`q<45;a@{}*)=xxik?cYyMk2^;_>&T0y!PLur>&S9`gTLun5I(i7n*-OH#p%S)@Q;-*d@J+s{m4rFd5}Rhe`+BNE6br#*0yG0"
    "{2=xZx~<lwm*&>bRy?Ct(0b{GT$kIXULM3z*ZS;x*(&vyew15r6h8H=DCT<iemV^%xfNvABwi+~9FQ#lWw-Uo4--GNW~*p|Kr(CW"
    "=MO%Rg{XcW{BnA}GdMrCmR@@2r<vuYK0rtUXb&*QfOu)m(s<blqFL(g+<EhP=<h()$PdNCfw<rMK}-}!#AGL3MUkI&lPAmZEa+x#"
    "d0FPCd1htt3YcU0f3CbR$e-N55d|q$0jeYaq1(Fj(++XRnt4G8J!N`Qe-futpa}3-A#z;u5dH*VXaP>kA%4dp5RKrbKGa$U5il>9"
    "xLq8-Rx4O0F)(_P-K)oimo36ztX}`f;z&I&y?mjb<4ipzfF8$3y=SX&lEyIRMUCvKc+CA}G7Cb#cn_B4bLvg}u{XI>A697ylyp<z"
    "53r<#Jhu{{0X|x?$|aK2I=VW&8C;znitA5@`|sXcean9P<BvZaeAwNe9K7}3y&F&ccW<ZOzBik^_jeEW4u14!Kg|5e-oc0Ihw=L#"
    "KKOgH591&Ay@PlAZ>K-}@NR5d)?ch~yaM)mxgm3MkZ4e$V7AJD>v>EpkD(}i2r|EQaeE`KE-r3>7NpUMvo0u4kb=z4{oJvCKN6~n"
    "-L`BcMGtX$7esU0brAwIF5v7~_Twy=>XK!*PR}o2$3vBLBtZn)fGDmnZm*68;`Ztcnm4p8%dz<)&y%dTvojC!#cJFIrP@io<-(gR"
    "f}Nw2V-Y90$fmO{l-mXDtHB8l2k<G|S@_;G+nK~u|51|C0d1NrI?G_rytP%clfli=CviNuy!iyp4|aE3f4@D00cKJQQvO(lffstw"
    "ypz4{7BAg6os+o=gJ|`*^Z5Q?XRo`r&$T=F*nQujvd-g&_u~CQH}}%+{EOW>xj^Jc7iYJh&#wW|uw}uI4W=qV4&-7bLVTD#3RWz7"
    "dD36L6ffL%ntF4sd>TJQWD>P+31~GMF`<Fw#%0M<WBo7M*ZUxw#H*|hq$qf5s;$vGYF*zP-VC7M&(LLW?%O@=J6PgXV!yOnt*Ji)"
    "0}i8%g%160TW{WgWdYlixjn*1FoqJq2!PR3S=3!6D87zrMI{eu01}PH#zDCUVfP>X$qHpckYVd$84yk&T%hGIRtJ9AT$gqk?DP{E"
    "XHwGN4mw9lQ?WL8VBvv{aL|xQil@OGO>SS=zOJkyNds|b-J&MlIPoLLPRF(jb{v{S)6i!)_=EG@IE*KERuEaxr_>3(<#_7#WKFPU"
    "-qhK%K7O?Jcipx%wr#g;T~edCM6j5U)X!IGq{<imBR@H=8X2NmjGtf{aG<d#0n2uk&QXO1DB4J1f7{l*7p{B>N@D}p%l*gP!OGp~"
    "YMEpXRc=Gyr!XP+_uDZ4q`A2BpR)c<3MEEQ*Zz1R`T>y_^-sJo^IhwE%l@CpRwRPuSpqX1FP($W5XN)Cl)h<OV8Qz5aRemb%o4Bi"
    "{@eGvyOR1O4I(gXSGVV=0hZnUBMu^G=_Me_Y1=|@u8U5{Dq9e_RRK__ln^{L%K)h7DnxlIr@}5sp`;f{gnz)Ae2N5e>(@C0)%`T>"
    "YcQ{GjzL+<uFAi!gPJV-$(`gaRSss7=q?Kj+Gwpm9?WRg)ha>+gEWm(XJ*Smu>8j$x1MXQUwYPag=dks^j~a4mMb+-H&~>6#FF)4"
    "-T?Pv;uk|7L|_fVP>?Bi#$E;^JwZuK110WW3KP=3uO>vS<Dx;KCWWQnQtwR{qzkV!^2KCSGXMQ9$pSDU0hiKmD>{^@tg#ml3-E@d"
    "#pv~m=BAn0(m<#mX=zA9^>Y6)@h9j8_Y0m4ZFIQ&Xljp!%poD^7R(HLqy(gHcdYOF1<Z}oV*hqv{T+c9g9DCQ2R*fAkS);#kYb@U"
    "duYQrp^|nUzszh@mDG_<UHp0^ztP~1+LoL%xC0<R;7R6PkSkjspIyd5m71kP`Ud1X&<9&}K8ka0*bQLLgdua>%{_)0DVX7sq3AjQ"
    "_0lKn0fYddNh<xRsS$)k3i}s7jYS9xrcl6IWFACf=_HE)x}JCw@Df4vy(o@?i5H5{8~b73zTbPV<`d~5M_`wqQ1YUrMc-k%4^RXE"
    "lJ(Kr?e6M*q{6NjJ?Z_!vZM=YhuE#3uuVlICGogG=)$V#70aQBww^2WzgXADCm;k7cm@%&3D!V!nAh)pNp%F4C6f%Bdr5{a8jyyo"
    "n&oQgAeAXNfW8xfm_$~`+Jk@kSJ!%@xMy?#r|k%*Z0I4Hfy8IIpMmiafC&(3c#5XlHza4cI~w-d7EeI<8$^@7?~R81QI?L}(nwQ<"
    "eN{nL8*#ZI8n8I_a)(hmim)LuW&|@NP%d9wWi1mg&A>|}cN3O)y3f<-)xe4q++x3PubbCAn1axHWcS@;SX*Dw2Z!sqy1a1JE@(hF"
    "MZ2G&tuVaniU2hm4I<q-y8hM5V9r{4ReM2A;|G$1XYew5l1c2d(5S*!>BHdgLgg-4zGddPFH{U4=sVFn(p7=rLJd>~d`J0b0ncVI"
    "=3rViECvF40SvBz0l>MhTFJ7*uwsX`a{h!QXc`f97&&9iOyhw#<j^Bn@!$vZ1(+DI^u5Tz(l+u#xxFi1bOH177-m)YtE>Ui9s0Ap"
    "ZKVhS>HiWW5(54n?)64mZ>BhlQq`ecB#l7v5JK@@)MZ@XBeHj(jSkfUs!)a*1iql6PV*9hq7~Z7&p0KiuOEr@ExG#u-YJa9f()^h"
    "#92TVCRsdXXo@=626_zhBk<T{Fw?$MAXW}(7$ga>nKg~!OJ>pX37x*F;yTo)xB^TDPOeJ?aT@Fl`aceO(2q0@^wd^j<byr;Q=Iro"
    "ph(x^hmz|*!C<;<Mofj|am=XXD|9dOmPrWeJB?W>d|2+wC{+={lMIDECg4!#wuu;}g|LrGD*HfX;|zikJ4b8M&<AL{`|TYVr|9qG"
    "Yq~(ArO}VFDS#ZQ2l$ABUeJd#%&4vRu~n{Nk_EaMPA)Y;=;MSwhf~0;DvepSRpAjEI)^P?P9gwbkT0@{<%45i0+PDL1ijJGQc1_G"
    ">AJP$gEXTkeyZwAtEG?ct~RzmF&8a1ec7<HrxkugDS1^-Q}02ugwxp1jIkSj*lq9a?~Y8}92Qzd_+4`u^k#@-SFy)PKNI`W)FL8t"
    "WI`ywqb`r6=3^X|V#{Izo+Q}WJPjt9)cpx9PnKnbT55Y~6F@$+;-Re@5TP4RDW5RSZSF?D(vLoMgg`8VDa_JVVRyO3_hg#b=m#mS"
    "hN>te?y9BvC?PWR3>ZQE*|Ig*DZM!qhv0y4Wfx)VY>_^eVPAz*Y=DKn8;A$fFJG9R*Cnkq0mkG2hBAn7XhT2urJTWnBbfTlL&n4i"
    "@YPclWfK@R%;flS=pFoAa{HAHA=RMZ;>h|h1s@!xT`AY|Rp_Ovat~@FpDLh8*J<LHe00!ZAzoJ@8~zT#Hg#P(J8~YEt<^LxU%%^1"
    "XiY(eb#4PAYb&heJk(G-m5yO>0Y?(`O$xSYOty<9p(zFcyR70S&pYzde);L6?4Ijx>#S8Km|2X$tLps1KzCFZt#lPCu_~OjLdUmr"
    "CrX_aTY@lL=C<|5kYkLpf=A<}LH>lnfQ1*%WW!9EBCzwWrtSZKc=tvsJ`k>!5xM)@#o)JyzgNYmF&zIjq4*lWhRFQZQF&>*!GFhI"
    "KhJD6IT-#ux&$wFugUALj1eyYTI=R_$>5g~tBNx{7j5i{0q*IhyIre>P=r1TJu8FtGFd47^Qb;+pqI1-?COx}2&!dYg=HFe^C-ss"
    "Qo)Kw!ud@dqV@_CzceF~s`c%d7=S`0-?r@3H*@k|=-xNu+|bb%w^+vhx$?kl=TB`V;*LYStJ(%wG&v>0MpL0r3Cud|0WP2GYS(C("
    "E6OK%u^vdXnXN#1Sj3^PfRM@#H(H5u-c*%!6RgWbrM2SZOF0^SjSri_>f^o*T#YxI0jGXQ5kjF&9H27+tW!$J1ky3Ao;S`MZ4f&;"
    "MwF?g_vm1qlD!}y*;Ce~b(aW0G`is51z{XXUnZM)<X=1J_k-~IQHBKG&BgL95b(z0@3YkR!5#3urC6eW2$QPy=8d&)+T@}(?u5yR"
    "rC8cr)h*4lGz2C~BkHd#ZxjX7dc0xU4XB0ie>Ld3(l)>^CeCjnzhR1Q#G>ZYZ$eU^wqNPVMwWH9>(7_%`t$9m8e9wmlLwM1OVFPq"
    "Ax!-lc(D<nqtfL*wAtAtpgPTysY$_C%I1!yx4d%IDSS<-j0gcCl?!(n6o(aF9DyI2iAfk|zVx!|OLnj_%?rN*LTQL{Fc_%^+>)ji"
    "tO$5jx&ImfRj&p>l8*uC(iU<gx}aM3hdCluaS?F!6(Z<9{B0vq^rDcK^9in&>d@<2-L^W6_sh58(BkPOo|*mZJqB4h6}+;U&20+x"
    "sWirjGF4DQ|CPYE>x}M3BYbi)U^sYP!V3~xTklq)H*%v#MUsIN0vw<v1+w@r3M9pq+EyVNW^PA~m$D^ga?uV5l}0p)agIi7o1Pcw"
    "%Kq>9oxR;!=j%Hyl4P~p;;Mul%&auibtp5ZNa%_D2MZGj<Y#0`h<nvuC}x<jAZDRAmx(5l37B5ONlUnKCwRdkD2W8j4f1~~;?$dj"
    "<kr!il$fX9Gytu`FDZs?GAfJ{AS?L7tFb&z;xL{+*)KY;gN%|8fGH~51%uWu$#muydr$p7)1^e6K6AtsM1*oL^o1AJb&H_lpQ|AC"
    "9rQ;6^mI@Fvdo*S4$B>?qI_edLN%4Zr>F`Tp27qmq*ubEZ8abHh$%b%)G2cdyXicP#}4HmPJ~Jw;EXI+Sy(0+J#h(%Sg_Z&W_FQx"
    "0Cvvu^4x>ssnq}tDpSVgvks<`G9o{Nf$t_T6GVBzG;dl!b7belG)N0gVG66cqTlr`TZqb6AxJJbb8I1Z?8lfQ%qgLm?pX$R6jn(n"
    "Zm6pK0-X+(!dYb@JCDKCpHQ%G+jcTrrIN~`XSW&sRyF!ol>;QWj9$yYal06^N*uSL3Ghadf|(q(EDlxHr}W`2ILy<GNYde(<P}|`"
    "+|yvWT;<*vV`Qi;n2SYZnzhOy5Mv*7i6_$)uMWzVrl~6_$2@A<*ae+d_$-)8^kiSVBHj&_$fSu<xo5$IT5}B>lgi8jiwdmeDnqeS"
    "2F@a|rnoEUQpzc<<f+hIRSGt!Ch*#qCaJ1s1kui0nHHp~Vy;W3HlbAYVWS+QUsn;7*IOwm9+k4I6TVsWnJRCRuW0xBIq7Onn9<v="
    "mkHeIeROzJK0%wSRZu4GjZOP$Ntx#JVhDi3)hAQ0dWK1Zc462gSio=(<|$5}fVZ<5o+O~eR9(D!*0Z#>67c_;a0}x{`6=F#CL7XY"
    "+zOVp)D){HYB05p3`H=c)C>tpR}^E9YpGd4qsrW48Js68QS{BJWZ&7geGRoa#W2Gxl4>HZ|2Xjz-hf@i&=XjzqbHA3Fimw2i(s-q"
    "-8IfQprXz_6jf)HL3J=!0oHfBc#eU$SRN}mmqdezS2@^((sLf#(S0xtyiT?ZD8;Pv=gLo?I?$~?@3j-7SF2#!UiwSuW0$u5+f1mC"
    "gmP0ln3DG=*?l{T7nDSTZZOiKWss_zW=1RkaTi+HMiMRllA13QT80xp3=1oa5`Z71+h|0>Fdv6ASO`ovOTeOFCJ!Z{@YdUCixj}x"
    "RL(gD{l2EdIQrmAgXc6N*QuBVZw@qxryA9HK|#hXLR_F#9AQce7-Cvqz}*d~gfh1ZVldm!{^jzP(;_sC6<j!cncR*X?$>eEx{7*7"
    "ja=$5e&W}{gIjfJ_a(#BDF<oj*i7dNp>pL`b>9gan#@D#0&~ZN4EJiJxplT;GIfwYt>Y)s`i#Ijb!acj4I`$Rx|X3c=*?m23^p{4"
    "Gdv@7A55xQMMD&I&XrCvT3%&koBIwUYEDvoy2;@`wKUz*qCw|U-h3z|lG_M6r~<Q3-NNZU7FR|$i69MaEY!lBicJYGkfdE_w@34q"
    "NX!|4nv>8r>YI3cT#KkO{2t9ja-Mno2Ml<fKF%`5!!p;$C&f9rn*-b62(KR{5aj*Ri-H-LYW<`DGp)a#XF~)vS~n#q5_gzHgK?ax"
    "y^bH8%*y?3a{e$x%AAhykejp1nYvX@Wa&h$9cWgZz#0t?4{67nL?QPwl@<L+(NsZ!`Ql>?d~G#@2qoe;$C!?4l~x8kv@r`0Q+9=7"
    "Q_Yzz2-e3XPB339P75+Bc2<3^A;1AxgPVl6p<(GvH8eF6x^){>r<EZvbM&ve<F68`0$dNlWbQu#5;Y3?iO{0ohE<UgSTPxR)W>17"
    "fUe0V|8`w|bCi5(QwCA<QYy>A0Z6`(6~GRys{;^Z9nLoPV~l8+L#sX(NjhMZqJ+fAAu{+NOA<`(LSLO_@iLVK-_v$Bat~=R1yRd-"
    "AKI#lw1yyZ<z$0t*_5E{WnP+kPh~48!A?%|r^N5uA7=-ZsUu3tbXKVAQkFN{#t_V&Q=~(aIZ*utxR~fCsD#Y|8-yN_LZ30Eg8_pZ"
    "lC7J%RIhmPM8mJ-lrUy8L!dm4pd;ghv9C>!6&!3PbtGlCRN*S6{OU%WRHY-USm<SWbALPBaT-t-e-&++1`j4s6t!5*E94iE_6m%t"
    "p9S+s!15;#kn}PlZ?1pKo^XqfY*ET!r7JL^Vp6Qm<nc0+HMA_jd=;;x)X~`lUDUvF=IZFjr+xcKnS6vfYlPVhsclIJCv~7F)fki{"
    "n1zR41XV4qW1X#7O&1A<f%PP*B{Z0(!JbB?aI9f3Y62cCS|=J{V0Z@M-VoYvXMrxFX#5bnvFtp*{BKDBpCtkAuRUL~l~nOU(v)^1"
    "J)U7o|9PCrcid@}oK${sfgST=KN@BRYRSSP6phttQ<#MP)0)P(a%7@QE**gbk6|x5b0XX08GBq}KJ)vFTgk8Y9@?_1I&(?3$&c>o"
    "B$1Hk`t*q_^F!_=I>~bC+GaArs}^KbMuB!!K|@Z?ZwKOfa5gx)85|4n^u_J%=`p5K=-Asv^`pb{i}TZ?!!to=YQ@>%&x12O@k__d"
    "ZR>lUDrvQ1w&eO8;XxdA8{JSH<j-t^lW=o`%TK4`NL*YU53bB6P0CzvdUA1fb9H!LZ@OM{iA+9uetmm&a(JY5@AcWiq~PN8{03WJ"
    "4v?Ac>M7GTbExZ9MrUw#wiOhN39JQD4DrR)=`W|};`3|3)=Wg}0Ur;pPk#YkUmhNvp8rA!&~4eqf>dA*e!pb#{d{<(Xhl$)tc3|d"
    "HoUnw8^HL(7}lv-XHc3U{eptK5r{G@X5NuB7oe%qO!&C_LmINy!Hrirc%OWn8P^ob(3EktPZ%vz3FjO}M$@M)Q1Q^p9J695RK}OC"
    ";GPR%{cEPKSHVbJ5jNAdq*cbcj0YLkNvnotv@F0T<`*-Z6h!y&9R-|*AqS=$w+K{FG)wi^2wPD`xDjw66+QbEZNkmqQk<Uudhw6J"
    "v1PmZCi#B=(beGQ_Uc^2B==S;i$)$lT-vHjY}6hs?~~P6i<9hL$T&v5F<+ZQVZv6!`dzhUCt2I<wTsh!g+HTDdgZB#M%RQRkJV#?"
    "1u`ixw6SaTzxMD0M`@MTRkI;57A#7LYqKd>vip`c_i6d|LSEVfI$H=HB?~iKrSDhDiczN7fO>jJ9A&6xApX7WlSed&)IZ50K}=WM"
    "`~YzKZGW9ca<iZ{uGx$Y|8moec9>;C0#z3)-UFxSM0;j|vkgn1gV!+?bmq&Sa$;sFXl7xXP6gAk4t-QXt)Q~X<JLg4!%&0<DzLX%"
    "2yy^VZ`ClzyPG_BBOS$n#BorO;$|<#-?sv%^==$bp9DY^$`<yTl$6ai?-XJS2H%h)RI9jw^al(phC%pLY*Y|bNyxCFyn&OG)zlMz"
    "glj-lOE*x%C-R%Ym}L!A6wz{!QZS$(s8gqCU53(0>UK5m->2RZIF3g?O!@G=JAs9~<U*Nst97WD_ItESa&qTwRZJ~K<K;a%Qa^`V"
    "XQWc%@u*PjuV`2#CXbYhA@3M@Hg#%+rq4dQ_<VUb0B6d^=?(1znN96vG94ST$-y}}JUxS&8Uv{^y1sNPn~9*HmI(tkKt+09R}p7b"
    "aFw*(`Y>1qxoU<hzKthBHn0V;>w2eoW+(ytST*aJh@kBGu2&4h-AFf-jme@$K6pdn=6u%n)@PL}M@H7svPIIVcAR8=CHF<+PAyZj"
    "<WNHvr+yj(uVmr;>8xt%j56HY;$v|&gO4Bexu>eEz0JDp)+g`M1?s)(B54Y)U4T@&WjyuBTW;i4RQzTJ2<Vf_NLtCetDLo=?6#$L"
    "$7DFX%@=^64_<^5j3vCf&qS!p1Zc;oudUVTtE9ZIZbsqD0d2YcuT|+T@8Gw?sZ^P^XRXCL0L)j#=e797*TzTqhL(6--#c5s(Pcw@"
    "{G)CAfv0bH)lh@3gE23e!Brixo9>k9$eYeO81?T*v5kInry~cZ|12L~<kd3((&Z=Mlzd`@xJ3=fw40tP7c_~?Tqb_i;&9U?NyVB`"
    "O5oCiWxkXX5QK)YZsYw;;F!jD+RzgtXeEUNcb9P#=NJ}n)ZssM16;8gBve+R+T<~lkLo#x)jYBF*?UxTtF)&oajHyR#iQ<x0mnfe"
    "rqo3bh**=@qNaV$h*!-q0g+dkXlZGs$%9H+E@)ZGj3yFgLEA|}xZ3qn>N?EsjgPxoV4;p-kvAdyVB%-NW8cP|QO<$lTUoG8xpRbS"
    "rIZCrw9`erTixd>XanejtsOrqSS3|z=9^cml-DugosQ5=Tq;oF%b!vUq<)rHFhNCuwMgAIKq{_qk`QnqLfA<ar+$(zWQF>TkWjh2"
    "nX-7k8l0G95WID_Ky6DD<q$zjMHl9H+3mVDLRbJ~WRjp-SGZARtgTB{+C)+6-*;$*j^&>QhsS2ZkxCe<?fjRiYio&bD<QG?OVf2b"
    "WpcwSX&yxjb>Y^=yW6zHhI{ieQp^!|jPfG<ZSy^B=eM85&8I71#kGvpZMfbnU!bkQlt$?7(e3e}`1SPq^yjky$kwl?M*{@W*ql~9"
    ";86u*&|;M+GkS5G^hq*FaHe=3c*P|G|DFlR?$GG3vLKpUmv{5O;jgZS&2gJfH%Q6U>Phve%~X3IbVd29%#?4*PWjJes7w}^KQ_f1"
    "dyrSn1EP&weju`Cd}oy6J9g&Z;x|YI+vw2n<+zfN!n1KVoL4a}z@v6+M|NKy+3|)%K)F{)cVPEn+<)8sSzLd<_y=gp#reQi>T_~?"
    "esptsaejDa<zRrQ`?v#zYtUO*ULGA@9{zlKc6#$q>v=r<YZ)?3ym5fnUjKFU(!4;LF@oc(Qw+w!ziU9lKu{NDKBkuhDu_UkRI{tw"
    "^PAJpgL=D^Pe&Myn$fd)(E%7S3j^KX&+3@U7|8}Czrh;(>g@FFpGNyym_{K()}9}J9#Ab61mQya{6ddh+YNI7o)e<8(<IZV*Yqlf"
    "xt@B+_10xrlz|9}$i5f`gOijsDW|0XZQj`<(_HAD2-PxoAI+>v(Dz=eeqf2H7?zDNq5NN3fi*3@%HAXta7J1Sr@l(4OmrU5AKI<S"
    "@LLaW7Eg?8-8)%4%X`*_``X)UE_vUQ5zks|h__=0zaN1s1=5CcLkkIvYunG5aNq!yZdZ_G34u4c!iN|8#XwfSvDsW5KbMPxVijIL"
    "Mk3dxJw-Q$Ho%$&UI^dNpLx-zO;FqhK}-2U8){!fxJ(h@ro(io_&{9YuM`u|N+>G$y|vfcx~I+OOEz`8TqJOf@*N8?>MVk(;fNF;"
    "E0aLQh3iS*62KU%84TtX>mJ^VFw@zE%C;A<*rRRDDF^7Fyn<0(_z&gkv8x^&G$H&yL>R^NMd6}Ke&{6`pv&a7CHgXxaztniTJ3CI"
    "TzJ?xB^^un0SYMYMD>Nb$Z1-XqwDajg-Q7ilQqUl50ViXO^1B+!D=d3o}zM@>gQEJxb$->y&^kVJF+5Ai{N6uJh4(evch>w<Rejv"
    "CbWB&9+Hw-o2KxWmo=BKo0S#G=3xecu<jmk-Qb*@o}XTS8XT)UlZ%T>d+orzRId!zFaL&aDyu}--3fsa4k2vTc4KDX*hg!VA#Q2j"
    ")3&jZW_}H>t}d=h%cu4I@bpY}mafz18}QX0*PLQDY<>k=Uetw}0p31%To`h6G!X_KVpadE2Eta)T|T!Wpbl=5AMEb#_VlF;-;_Qh"
    "^2O2F#r5DAW`PZJLz~VH^)dOI?<sf9BdM+b16mv=O#"
)
INPUT_ROOT = Path(os.environ.get("XC_INPUT", "/kaggle/input"))
matches = sorted(INPUT_ROOT.rglob("xfidc_criteria.json"))
if len(matches) != 1:
    raise RuntimeError(f"expected one attached FD-08 calibration criteria file, found {len(matches)}")
criteria_path = matches[0]
sidecar = criteria_path.with_suffix(criteria_path.suffix + ".sha256")
criteria_sha = hashlib.sha256(criteria_path.read_bytes()).hexdigest()
if not sidecar.is_file() or sidecar.read_text().strip() != criteria_sha:
    raise RuntimeError("FD-08 calibration criteria SHA-256 sidecar mismatch")
criteria = json.loads(criteria_path.read_text())
if (criteria.get("kind") != "fd08_candidate_c_calibration"
        or criteria.get("immutable") is not True
        or criteria.get("registered_before_computation") is not True
        or criteria.get("status") != "registered_not_run"):
    raise RuntimeError("attached criteria are not an immutable premeasurement FD-08 calibration")

source_inputs = criteria.get("source_inputs", {})
wrapper_binding = source_inputs.get("kernel_wrapper", {})
core_binding = source_inputs.get("kernel_base_runner", {})
if (not isinstance(wrapper_binding, dict) or not isinstance(core_binding, dict)
        or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != wrapper_binding.get("sha256")):
    raise RuntimeError("uploaded FD-08 calibration kernel wrapper hash mismatch")
core_source = zlib.decompress(base64.b85decode(_CORE_SOURCE_B85.encode("ascii")))
if hashlib.sha256(core_source).hexdigest() != core_binding.get("sha256"):
    raise RuntimeError("embedded FD-08 calibration core runner hash mismatch")

with tempfile.TemporaryDirectory(prefix="fd08_calibration_core_") as temp:
    core_path = Path(temp) / "runner_base.py"
    core_path.write_bytes(core_source)
    namespace = runpy.run_path(core_path, run_name="fd08_xfid_runner_core")
    namespace["CRITERIA_SHA256"] = criteria_sha
    namespace["INPUT_ROOT"] = INPUT_ROOT
    namespace["OUT"] = Path(os.environ.get("FD08_OUT_ROOT", "/kaggle/working")) / "fd08_calibration"
    namespace["main"]()
