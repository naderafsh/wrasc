from wrasc import ppmac_ra as ppra
from argparse import Namespace


boom = 4
JogSpeed = 1.28

motor = ppra.axis(8)

Attack_Pos_Enc = 9898

# this sets LVars into locals...
locals().update(motor.LVars())

test_stats = {
    "#{L7}p > {Attack_Pos_Enc} + Motor[L7].CapturedPos": [
        "#16p > 9898 + Motor[16].CapturedPos"
    ],
    "Motor[{L1}].JogSpeed={JogSpeed}": ["Motor[8].JogSpeed=1.28"],
    "Motor[L7].EncType=Gate[L2].Blaaa": ["Motor[16].EncType=Gate[1].Blaaa"],
    "#{L1}j=#{L3}p - 100": ["#8j=#3p - 100"],
    " // blah jjjs": [],
}

for stat in test_stats:
    stat_out = ppra.expand_pmac_stats(stat, **locals())
    assert test_stats[stat] == stat_out

print("expand_pmac_stats test 1 passed.")


cmds = 'disable plc 10\nOPEN plc 10\nif (Plc[3].Running==0)\n{\n    cmd "&1p q81=d0 q82=d1 q83=d2 q84=d3 q85=d4 q86=d5 q87=d6 q88=d7 q89=d8"\n}\nclose\nenable plc 10'.splitlines()

parsed_cmds = ppra.parse_cmds(cmds).splitlines()

assert parsed_cmds == cmds, f"\nExpected: {parsed_cmds} \nActual: {cmds}"


given_1 = 1
given_2 = 2
# ungiven = 4


test_stats = {
    "int(#{L1}p/{smalljog_steps}/2)<1": ["int(#1p/5/2)<1"],
    "{given_1} = {{given_2}} - {{given_1}}": ["1 = {given_2} - {given_1}"],
    "{given_1} = {{ungiven}} - {{given_1}}": ["1 = {ungiven} - {given_1}"],
    f"{given_1} = {{given_2}} - {{given_1}}": ["1 = 2 - 1"],
    f"{given_1} = {{ungiven}} - {{given_1}}": ["1 = {ungiven} - {given_1}"],
}

L1 = 1
smalljog_steps = 5

for stat in test_stats:
    stat_out = ppra.expand_pmac_stats(stat, **locals())
    assert test_stats[stat] == stat_out

print("expand_pmac_stats test 2 passed.")

# now testing pars_cond function
testing_func = ppra.parse_stats

test_stats = {
    "int(#1p/5/2)<1": [["int(_var_0/5/2)<1", ["#1p"], "int(#1p/5/2)<1"]],
    "EncTable[L1].ScaleFactor=1 / (256 )": [
        [
            "_var_0=1/(256)",
            ["EncTable[L1].ScaleFactor"],
            "EncTable[L1].ScaleFactor=1/(256)",
        ]
    ],
    "EncTable[L1].ScaleFactor=1 / (256 * (EncTable[L1].index5 + 1) * EXP2(EncTable[L1].index1))": [
        [
            "_var_0=1/(256*(_var_1+1)*2**(_var_2))",
            ["EncTable[L1].ScaleFactor", "EncTable[L1].index5", "EncTable[L1].index1"],
            "EncTable[L1].ScaleFactor=1/(256*(EncTable[L1].index5+1)*EXP2(EncTable[L1].index1))",
        ]
    ],
    "EncTable[L7].pEnc = PowerBrick[L4].Chan[L5].ServoCapt.a": [
        [
            "_var_0='PowerBrick[L4].Chan[L5].ServoCapt.a'",
            ["EncTable[L7].pEnc"],
            "EncTable[L7].pEnc=PowerBrick[L4].Chan[L5].ServoCapt.a",
        ]
    ],
    "Motor[L1].AdcMask=4294705152": [  # TODO: make it work with $FFFC0000
        ["_var_0=4294705152", ["Motor[L1].AdcMask"], "Motor[L1].AdcMask=4294705152"]
    ],
    "Motor[L1].PwmSf=16372.8846675712": [
        [
            "_var_0=16372.8846675712",
            ["Motor[L1].PwmSf"],
            "Motor[L1].PwmSf=16372.8846675712",
        ]
    ],
}


out_stats = list(map(testing_func, test_stats))

for stat in test_stats:
    stat_outs = testing_func(stat)[0]
    for i, stat_out in enumerate(stat_outs):
        expected = test_stats[stat][0][i]
        assert expected == stat_out, f"\nExpected: {expected} \nActual: {stat_out}"


print("pars_cond passed.")

