import regex as re


"""
it seems that the capture flag is being consumed, 
as only one capture can be RELIABLY done upon one flag fall
example:

Motor[3].JogSpeed=2.4 #3j-
#11kill
#11j:+6274^10 Motor[11].CapturePos=1
Motor[3].JogSpeed=0.1 #3j:+2000    

captures Motor[11], but not Motor[3]

opposite:

Motor[L1].JogSpeed=2.4 #3j-
#11kill
#11j:+6274^10 Motor[11].CapturePos=1
Motor[3].JogSpeed=0.1 #3j:+2000^100

and 

Motor[L1].JogSpeed=2.4 #3j-
#11kill
#11j:+6274^10 Motor[11].CapturePos=1
Motor[3].JogSpeed=0.1 #3j:+2000 Motor[3].CapturePos=1    

only capture Motor[3], not Motor[11]


"""


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
    "Motor[L7].JogSpeed=0.02",
]

verify_config_rdb_lmt = [
    cond.replace("=", "==") if ("=" in cond) else cond for cond in config_rdb_lmt
]

jog_capt_rbk_tl = [
    "#{L1}j:{SlideOff_Dir}2000^{Trig_Offset} #{L7}j:10^0",
]

cond_on_neg_lim = ["Motor[L1].MinusLimit>0", "Motor[L1].InPos>0"]

check_off_limit_inpos_tl = [
    "Motor[L1].MinusLimit==0",
    "Motor[L1].PlusLimit==0",
    "Motor[L1].InPos>0",
]
log_capt_rbk_tl = [
    # readback capture via companion axis
    "Motor[L7].CapturedPos",
    # readback and step position at stop position
    "#{L7}p",
    "#{L1}p",
    # test condition parameter
    "Motor[L1].JogSpeed",
    "full_current(L1)",
    "Motor[L1].IdCmd",
    # position references
    "Motor[L1].HomePos",
    "Motor[L1].HomeOffset",
    "Motor[L7].HomePos",
    # these will give ILLEGAL CMD errors
    "{enc_res}",
    "{step_res}",
    # Check these for errors
    "Motor[L7].CapturePos",
    "Motor[L1].TriggerNotFound",
    "Motor[L7].TriggerNotFound",
    "PowerBrick[L2].Chan[L3].CountError",
]

reset_rbk_capt_tl = [
    "Motor[L1].JogSpeed={JogSpeed}",
    "Motor[L1].CaptureMode=1",  # reset capture mode to default baseConfig
    "#{L1}hmz",
    "PowerBrick[L2].Chan[L3].CountError=0",
]
