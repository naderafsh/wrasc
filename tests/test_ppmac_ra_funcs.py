from wrasc import ppmac_ra as ppra


boom = 4
L7 = 11
L1 = 3
JogSpeed = 1.28


test_stat = [
    "Motor[L7].EncType=Motor[{boom}].EncType",
    "Motor[{L1}].JogSpeed={JogSpeed}",
    "#{L1}j={#{boom}p - 100}",
]

expanded_stat = [
    "Motor[11].EncType=Motor[4].EncType",
    "Motor[3].JogSpeed=1.28",
    "#3j={#4p - 100}",
]


expanded_stat_out = ppra.expand_pmac_stats(test_stat, **locals())

assert expanded_stat == expanded_stat_out

print("test passed!")

