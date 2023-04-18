# This file was auto-generated. Do not manually edit or save. What are you doing looking at it? Close it now!
# Generated on 2023-04-18 17:45:14.509889
#
import binascii
import io

fwver = 0, 66
def getsome(item, filelike=True):
    data = _contents[item].encode('latin-1')
    data = binascii.a2b_base64(data)
    if filelike:
        data = io.BytesIO(data)
    return data

_contents = {

#Contents from ../../../../hardware/capture/chipwhisperer-nano/firmware/cwnano-firmware/src/ChipWhisperer-Nano.bin
'SAM3U_CWNANO.bin':'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',

}
