from wrasc import ppmac_ra as ppra

gpascii = ppra.PpmacToolMt(host="10.109.25.22")
gpascii.connect()
assert gpascii.connected
