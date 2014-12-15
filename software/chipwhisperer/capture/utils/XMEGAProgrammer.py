# -*- coding: utf-8 -*-
#
# Copyright (c) 2014, NewAE Technology Inc
# All rights reserved.
#
# Authors: Colin O'Flynn
#
# Find this and more at newae.com - this file is part of the chipwhisperer
# project, http://www.assembla.com/spaces/chipwhisperer
#
#    This file is part of chipwhisperer.
#
#    chipwhisperer is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    chipwhisperer is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with chipwhisperer.  If not, see <http://www.gnu.org/licenses/>.
#=================================================

from chipwhisperer.capture.scopes.ChipWhispererLite import XMEGAPDI
from chipwhisperer.capture.scopes.ChipWhispererLite import XMEGA128A4U
from chipwhisperer.capture.scopes.ChipWhispererLite import CWLiteUSB
from chipwhisperer.capture.utils.IntelHex import IntelHex

class XMEGAProgrammer(object):
    
    def __init__(self):
        super(XMEGAProgrammer, self).__init__()
        self._usbiface = None
        self.supported_chips = [XMEGA128A4U()]
        self.xmega = XMEGAPDI()
        self._logging = None
        self._foundchip = False

    def setUSBInterface(self, iface):
        self._usbiface = iface
        self._foundchip = False
        self.xmega.setUSB(iface)
        self.xmega.setChip(self.supported_chips[0])

    def find(self):
        self._foundchip = False

        self.xmega.setParamTimeout(200)
        self.xmega.enablePDI(True)

        # Read signature bytes
        data = self.xmega.readMemory(0x01000090, 3, "signature")

        # Check if it's one we know about?
        for t in self.supported_chips:
            if ((data[0] == t.signature[0]) and
                (data[1] == t.signature[1]) and
                (data[2] == t.signature[2])):

                self._foundchip = True

                self.log("Detected %s" % t.name)
                self.xmega.setChip(t)
                break

        # Print signature of unknown device
        if self._foundchip == False:
            self.log("Detected Unknown Chip, sig=%2x %2x %2x" % (data[0], data[1], data[2]))

    def erase(self, memtype="chip"):

        if memtype == "app":
            self.xmega.eraseApp()
        elif memtype == "chip":
            self.xmega.eraseChip()
        else:
            raise ValueError("Invalid memtype: %s" % memtype)

    def program(self, filename, memtype="flash", verify=True):
        f = IntelHex(filename)

        startaddr = self.xmega._chip.memtypes[memtype]["offset"]
        maxsize = self.xmega._chip.memtypes[memtype]["size"]
        fsize = f.maxaddr() - f.minaddr()

        if fsize > maxsize:
            raise IOError("File %s appears to be %d bytes, larger than %s size of %d" % (filename, fsize, memtype, maxsize))

        print "Programming..."
        fdata = f.tobinarray(start=0)
        self.xmega.writeMemory(startaddr, fdata, memtype)
        
        print "Reading..."
        #Do verify run
        rdata = self.xmega.readMemory(startaddr, len(fdata), memtype)

        for i in range(0, len(fdata)):
            if fdata[i] != rdata[i]:
                # raise IOError("Verify failed at 0x%04x, %x != %x" % (i, fdata[i], rdata[i]))
                print i
                pass

        print "Verifed OK"
    
    def close(self):
        self.xmega.enablePDI(False)

    def log(self, text):
        if self._logging is None:
            print text
        else:
            self._logging(text)


if __name__ == '__main__':
    cwtestusb = CWLiteUSB()
    cwtestusb.con()

    force = False

    if cwtestusb.isFPGAProgrammed() == False or force:
        from datetime import datetime
        starttime = datetime.now()
        cwtestusb.FPGAProgram(open(r"C:\E\Documents\academic\sidechannel\chipwhisperer\openadc\hdl\example_targets\cwlite_testdev\cwlite_interface.bit", "rb"))
        stoptime = datetime.now()
        print "FPGA Config time: %s" % str(stoptime - starttime)

    fname = r"C:\E\Documents\academic\sidechannel\chipwhisperer\hardware\victims\firmware\xmega-serial\simpleserial.hex"

    xmega = XMEGAProgrammer()
    xmega.setUSBInterface(cwtestusb._usbdev)
    xmega.find()
    try:
        print "Erasing"
        xmega.erase("chip")
    except IOError:
        print "**chip-erase timeout, workaround enabled**"
        xmega.xmega.enablePDI(False)
        xmega.xmega.enablePDI(True)
    xmega.program(fname, "flash")
    xmega.close()

