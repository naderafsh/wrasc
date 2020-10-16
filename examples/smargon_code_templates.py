def assert_pos_wf(xx: int, target_pos, tol):
    """

    retuns 
    1 - assert condition for motor xx at resting at position pos+_tol
    2 - default jog statement to move the motor there if not already there

    """
    if isinstance(target_pos, str) or isinstance(tol, str):
        tol = str(tol)
        target_pos = str(target_pos)
        pos_hi = f"{target_pos} + {tol}"
        pos_lo = f"{target_pos} - {tol}"

    else:
        pos_hi = target_pos + tol
        pos_lo = target_pos - tol

    return (
        [
            f"#{xx}p < {pos_hi}",
            f"#{xx}p > {pos_lo}",
            f"Motor[{xx}].InPos==1",
            f"Motor[{xx}].MinusLimit + Motor[{xx}].PlusLimit == 0",
        ],
        [f"#{xx}jog=={target_pos}"],
    )

def cry_for(conds):
    cry_list = [cond.replace("=", "==") if ("=" in cond) else cond for cond in conds]
    return cry_list

prog10_code = r"OPEN PROG 10\nLINEAR\nABS\nTM(Q70)\nA(Q71)B(Q72)C(Q73)X(Q77)Y(Q78)Z(Q79)\nDWELL0\nCLOSE"
plc10_code = r'open plc 10\nif (Plc[3].Running==0)\n{\n    cmd "&1p q81=d0 q82=d1 q83=d2 q84=d3 q85=d4 q86=d5 q87=d6 q88=d7 q89=d8"\n}\nclose\n \nenable plc 10'
limit_cond = "Motor[6].pLimits=0"

pre_cond = [limit_cond]
cs_code = [prog10_code, plc10_code]


config_rdb_lmt = [
    # "Motor[L7].PosSf = {encoder_possf}",
    # "EncTable[L7].ScaleFactor = -1/256",
    # put EncType first, as it resets pCaptFlag and pCaptPos !!!!
    "Motor[L7].EncType=Motor[L1].EncType",
    "Motor[L7].CaptControl=Motor[L1].CaptControl",
    "Motor[L7].pCaptFlag=Motor[L1].pCaptFlag",
    "Motor[L7].pCaptPos=Motor[L1].pCaptPos",
    "Motor[L7].LimitBits=Motor[L1].LimitBits",
    "Motor[L7].CaptureMode=1",
    "Motor[L7].pLimits=0",
    "Motor[L7].MotorTa=-10",
    "Motor[L7].MotorTs=-50",
    # "#{L7}$,",
    # "#{L7}j/",
    # set the following error of the companion axis out of the way
    "Motor[L7].FatalFeLimit=9999999",
    "Motor[L1].CaptureMode=0",
    "PowerBrick[L2].Chan[L3].CaptCtrl=10",
    "Motor[L1].JogSpeed={JogSpeed}",
]

verify_config_rdb_lmt = [
    cond.replace("=", "==") if ("=" in cond) else cond for cond in config_rdb_lmt
]

jog_capt_rbk_tl = [
    "Motor[L7].CapturePos=1",
    "Motor[L1].JogSpeed={HomeVel}",
    "#{L1}j:{CaptureJogDir}2000^{trigOffset}",
    # companion axis is fooled to think it is jogging
    "Motor[L7].JogSpeed=0.00001",
    "#{L7}j:10^0",
]


check_on_aux = ["Motor[L1].pAuxFault > 0","Motor[L1].AuxFault > 0","Motor[L1].InPos>0"]
slideoff_capt = ["Motor[3].pCaptFlag = Motor[3].pAuxFault","Motor[3].CaptFlagBit = 8", "Motor[3].pAuxFault = 0", "Motor[3].AuxFaultLevel = 0"]


check_off_limit_inpos_tl = [
    "Motor[L1].MinusLimit==0",
    "Motor[L1].PlusLimit==0",
    "Motor[L1].InPos>0",
]
log_capt_rbk_tl = [
    # main axis
    "Motor[L1].HomePos",
    "Motor[L1].CapturedPos",
    "#{L1}p",
    # companion axis used for readback
    "Motor[L7].HomePos",
    "Motor[L7].CapturedPos",
    "#{L7}p",
    # test condition parameter
    "Motor[L1].JogSpeed",
    "full_current(L1)",
    "Motor[L7].CapturePos",
    "Motor[L1].TriggerNotFound",
    "Motor[L7].TriggerNotFound",
]

reset_rbk_capt_tl = [
    "Motor[L1].JogSpeed={JogSpeed}",
    "#{L7}j/",
]
