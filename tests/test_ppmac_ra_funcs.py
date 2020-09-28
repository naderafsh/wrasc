from wrasc import ppmac_ra as ppra
from argparse import Namespace


boom = 4
JogSpeed = 1.28

motor = ppra.axis(8)

# this sets LVars into locals...
locals().update(motor.LVars())

test_stat = [
    "Motor[{L1}].JogSpeed={JogSpeed}",
    "Motor[L7].EncType=Gate[L2].Blaaa",
    "#{L1}j=#{L3}p - 100",
]

expanded_stat = [
    "Motor[8].JogSpeed=1.28",
    "Motor[16].EncType=Gate[1].Blaaa",
    "#8j=#3p - 100",
]


expanded_stat_out = ppra.expand_pmac_stats(test_stat, **locals())
assert expanded_stat == expanded_stat_out
print("test 1 passed!")


expanded_stat_out = motor.expand_stats(test_stat[1:])
assert expanded_stat[1:] == expanded_stat_out
print("test 1.5 passed!")


given_1 = 1
given_2 = 2
# ungiven = 4


test_stat = [
    "{given_1} = {{given_2}} - {{given_1}}",
    "{given_1} = {{ungiven}} - {{given_1}}",
    f"{given_1} = {{given_2}} - {{given_1}}",
    f"{given_1} = {{ungiven}} - {{given_1}}",
]

expanded_stat = [
    "1 = {given_2} - {given_1}",
    "1 = {ungiven} - {given_1}",
    "1 = 2 - 1",
    "1 = {ungiven} - {given_1}",
]

expanded_stat_out = ppra.expand_pmac_stats(test_stat, **locals())
assert expanded_stat == expanded_stat_out
print("test 2 passed!")

