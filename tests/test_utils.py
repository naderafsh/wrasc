import utils as ut


def test_ShortHand_init():

    epics_motor_field_fs = [
        [r"SR\d\d", ""],  # Section designator, starts with "SR"
        [r"ID\d\d", ""],  # ID designator starts with "ID"
        [r"[A-Z]{3}\d\d[:]{1}", ""],  # Device designator, ends with ":"
        [r"[\w_]+", ""],  # Motor () designator
        [r"[.:]{1}[A-Z_]+", ""],  # Motor field, starts with either "." or ":"
    ]

    sh = ut.ShortHand(group_formats=epics_motor_field_fs)

    assert (
        sh.full_expression
        == r"(SR\d\d)*(ID\d\d)*([A-Z]{3}\d\d[:]{1})*([\w_]+)*([.:]{1}[A-Z_]+)*"
    )
    assert len(sh.text_groups) == 5

    assert sh.long("SR05ID01DEV02:MOT_MTR01.PVA") == "SR05ID01DEV02:MOT_MTR01.PVA"

    assert sh.long("MOT_02") == "SR05ID01DEV02:MOT_02.PVA"

    assert sh.long(":XPV") == "SR05ID01DEV02:MOT_02:XPV"

    assert sh.long("MOT_03.IPV") == "SR05ID01DEV02:MOT_03.IPV"

    assert sh.long("DEV03:") == "SR05ID01DEV03:MOT_03.IPV"

    assert sh.long("ID04DEV04:MOT_04.IPV") == "SR05ID04DEV04:MOT_04.IPV"

    assert sh.long("SR06") == "SR06ID04DEV04:MOT_04.IPV"


if __name__ == "__main__":
    test_ShortHand_init()
    print("\n\n\nall tests passed.\n\n\n")
