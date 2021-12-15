# pylint skip-file
#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2020-2021, NewAE Technology Inc
# All rights reserved.
#
# Find this and more at newae.com - this file is part of the chipwhisperer
# project, http://www.chipwhisperer.com . ChipWhisperer is a registered
# trademark of NewAE Technology Inc in the US & Europe.
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
import time
import re
import math
import pkg_resources # type: ignore
import chipwhisperer as cw
from ...common.utils import util
#from ...hardware.naeusb.naeusb import NAEUSB
#from ...hardware.naeusb.fpga import FPGA

import phywhisperer.interface.naeusb as NAE
import phywhisperer.interface.program_fpga as LLINT

from ..scopes.cwhardware.ChipWhispererHuskyMisc import XilinxDRP, XilinxMMCMDRP
from ...logging import *
from collections import OrderedDict
import numpy as np

CODE_READ       = 0x80
CODE_WRITE      = 0xC0

class TraceWhisperer(util.DisableNewAttr):

    """ Trace interface object.

    This class contains the public API for the Arm Coresight trace sniffing
    hardware, which may exist on either the CW305 or the CW610 (PhyWhisperer)
    platform.

    To connect, the easiest method is::

        (a) CW305 (DesignStart) case:
        import chipwhisperer as cw
        from chipwhisperer.capture.trace.TraceWhisperer import TraceWhisperer
        scope = cw.scope()
        target = cw.target(scope, targets.CW305, bsfile=<valid FPGA bitstream file>)
        trace = TraceWhisperer(target, scope)

        (b) CW610 (PhyWhisperer) case:
        import chipwhisperer as cw
        from chipwhisperer.capture.trace.TraceWhisperer import TraceWhisperer
        scope = cw.scope()
        target = cw.target(scope)
        trace = TraceWhisperer(target)

    """

    _name = "TraceWhisperer"

    rule_length = [0]*8

    longsync = [255, 255, 255, 127]
    shortsync = [255, 127]

    def __init__(self, target, scope, defines_files=None, bs='', force_bitfile=False):
        """
        Args:
            target: SimpleSerial target object
            scope: CW scope object
            bs (string): FPGA bitfile (default is used if not specified)
            defines_files (list of 2 strings): path to defines_trace.v and defines_pw.v
            force_bitfile (bool): force loading of FPGA bitfile, even if FPGA is already programmed.
        """
        super().__init__()
        self._trace_port_width = 4
        self._base_target_clock = 7.384e6
        self._base_baud = 38400
        self._usb_clock = 96e6
        self._uart_clock = self._usb_clock * 2
        self.expected_verilog_defines = 117
        self.swo_mode = False
        self._scope = scope
        # Detect whether we exist on CW305 or CW610 based on the target we're given:
        if target._name == 'Simple Serial':
            self.platform = 'CW610'
            self._ss = target
            self._naeusb = NAE.NAEUSB()
            self._naeusb.con(idProduct=[0xC610])
            # we're using the CW NAEUSB, which has no knowledge of PW firmware, so let's manually
            # check the FW version here:
            fw_latest = [1,1]
            if self._naeusb.readFwVersion()[0] < fw_latest[0]:
                tracewhisperer_logger.warning('Your PhyWhisperer firmware is outdated - latest is %d.%d' % (fw_latest[0], fw_latest[1]) +
                                     '. Suggested to update firmware, as you may experience errors.')

            #self._fpga = FPGA(self._naeusb)
            self._fpga = LLINT.PhyWhispererUSB(self._naeusb)
            if not self._fpga.isFPGAProgrammed() or force_bitfile:
                if not bs:
                    bs = pkg_resources.resource_filename('chipwhisperer', 'hardware/firmware/tracewhisperer_top.bit')
                self._fpga.FPGAProgram(open(bs, 'rb'), exceptOnDoneFailure=False)
        else:
            self.platform = 'CW305'
            self._ss = cw.target(scope)
            self._naeusb = target._naeusb

        self.slurp_defines(defines_files)
        self.target_registers = ARM_debug_registers(self._ss)
        self.clock = clock(self)
        self.capture = capture(self)

        if self.board_rev == 3:
            self.tms_bit = 0
            self.tck_bit = 2
            tracewhisperer_logger.warning("Using FPGA bitfile built for rev-3 board, make sure this is what you intend!")
        elif self.board_rev == 4:
            self.tms_bit = 0
            self.tck_bit = 1

        self.disable_newattr()
        self._set_defaults()

    def sendMessage(self, mode, address, payload=None, Validate=False, maxResp=None, readMask=None):
        """ This exists only so that borrowed classes from ChipWhisperer can work. For "native" trace work,
            use fpga_read() / fpga_write() directly instead.
        """
        if Validate or readMask:
            raise ValueError("Not implemented!")
        if mode == CODE_READ:
            return self.fpga_read(address, maxResp)
        elif mode == CODE_WRITE:
            return self.fpga_write(address, payload)


    def _dict_repr(self):
        rtn = OrderedDict()
        rtn['fpga_buildtime']   = self.fpga_buildtime
        rtn['errors']           = self.errors
        rtn['trace_synced']     = self.trace_synced
        rtn['trace_mode']       = self.trace_mode
        if self.trace_mode == 'SWO':
            rtn['swo_div']      = self.swo_div
        else:
            rtn['trace_width']  = self.trace_width
        if self.platform == 'CW610':
            rtn['leds']             = self.leds
        rtn['clock']            = self.clock._dict_repr()
        rtn['capture']          = self.capture._dict_repr()
        rtn['target_registers'] = self.target_registers._dict_repr()

        return rtn


    def __repr__(self):
        return util.dict_to_str(self._dict_repr())

    def __str__(self):
        return self.__repr__()


    def _set_defaults(self):
        """ Set some registers which for various reasons don't reset to what we want them to.
        """
        self.fpga_write(self.REG_CAPTURE_WHILE_TRIG, [1])
        # TODO- temporary for development:
        self.fpga_write(self.REG_REVERSE_TRACEDATA, [0])


    def reset_fpga(self):
        """ Reset FPGA registers to defaults, use liberally to clear incorrect states.
            On the CW305, this resets the full FPGA, including the target Arm core.
        """
        self.fpga_write(self.REG_RESET_REG, [1])
        self.fpga_write(self.REG_RESET_REG, [0])
        self._set_defaults()


    def slurp_defines(self, defines_files=None):
        """ Parse Verilog defines file so we can access register and bit
        definitions by name and avoid 'magic numbers'.
        """
        self.verilog_define_matches = 0
        if not defines_files:
            defines_files = [pkg_resources.resource_filename('chipwhisperer', 'capture/trace/defines/defines_trace.v'),
                             pkg_resources.resource_filename('chipwhisperer', 'capture/trace/defines/defines_pw.v')]
        for i,defines_file in enumerate(defines_files):
            defines = open(defines_file, 'r')
            define_regex_base  =   re.compile(r'`define')
            define_regex_reg   =   re.compile(r'`define\s+?REG_')
            define_regex_radix =   re.compile(r'`define\s+?(\w+).+?\'([bdh])([0-9a-fA-F]+)')
            define_regex_noradix = re.compile(r'`define\s+?(\w+?)\s+?(\d+?)')
            for define in defines:
                if define_regex_base.search(define):
                    reg = define_regex_reg.search(define)
                    match = define_regex_radix.search(define)
                    if reg:
                        if i == 0:
                            block_offset = self.TRACE_REG_SELECT << 6
                        else:
                            block_offset = self.MAIN_REG_SELECT << 6
                    else:
                        block_offset = 0
                    if match:
                        self.verilog_define_matches += 1
                        if match.group(2) == 'b':
                            radix = 2
                        elif match.group(2) == 'h':
                            radix = 16
                        else:
                            radix = 10
                        setattr(self, match.group(1), int(match.group(3),radix) + block_offset)
                    else:
                        match = define_regex_noradix.search(define)
                        if match:
                            self.verilog_define_matches += 1
                            setattr(self, match.group(1), int(match.group(2),10) + block_offset)
                        else:
                            tracewhisperer_logger.warning("Couldn't parse line: %s", define)
            defines.close()
        # make sure everything is cool:
        assert self.verilog_define_matches == self.expected_verilog_defines, "Trouble parsing Verilog defines file (%s): didn't find the right number of defines; expected %d, got %d" % (defines_file, self.expected_verilog_defines, self.verilog_define_matches)


    @property 
    def trace_mode(self):
        """Set trace or SWO mode. SWO mode is only available on CW610 platform.
        Args:
            mode (string): 'parallel' or 'swo'
        """
        if self.swo_mode:
            return "SWO"
        else:
            return "parallel"

    @trace_mode.setter 
    def trace_mode(self, mode):
        if mode in ['swo', 'SWO']:
            self.swo_mode = True
            self.fpga_write(self.REG_SWO_ENABLE, [1])
            self.target_registers.TPI_SPPR = '00000002'
        elif mode == "parallel":
            self.swo_mode = False
            self.fpga_write(self.REG_SWO_ENABLE, [0])
            self.target_registers.TPI_SPPR = '00000000'



    def set_trace_mode(self, mode, swo_div=8, acpr=0):
        """Set trace or SWO mode. SWO mode is only available on CW610 platform.
        For SWO mode, we also adjust the target clock to match the SWO parameters.
        Args:
            mode (string): 'trace' or 'swo'
            swo_div (int): number of 96 MHz clock cycles per SWO bit (SWO mode only)
            acpr (int): value for TPI.ACPR register (SWO mode only)
        """
        tracewhisperer_logger.warning('Deprecated, use trace.trace_mode instead.')
        if mode == 'trace':
            self.swo_mode = False
            self.target_registers.TPI_SPPR = '00000000'
            self.fpga_write(self.REG_SWO_ENABLE, [0])
        elif mode in ['swo', 'SWO']:
            if self.platform == 'CW305':
                raise ValueError('CW305 does not support SWO mode')
            self.swo_mode = True
            self.target_registers.TPI_SPPR = '00000002'
            self.target_registers.TPI_ACPR = acpr
            self.fpga_write(self.REG_SWO_BITRATE_DIV, [swo_div-1]) # not a typo: hardware requires -1; doing this is easier than fixing the hardware
            self.fpga_write(self.REG_SWO_ENABLE, [1])
            # Next we set the target clock and update CW baud rate accordingly:
            new_target_clock = int(self._uart_clock / (swo_div * (acpr+1)))
            self._scope.clock.clkgen_freq = new_target_clock
            self._ss.baud = int(self._base_baud * (new_target_clock/self._base_target_clock))
            #self.swo_target_clock_ratio = self._usb_clock / new_target_clock
            tracewhisperer_logger.info("Ensure target is in SWD mode, e.g. using jtag_to_swd().")
        else:
            tracewhisperer_logger.error('Invalid mode %s: specify "trace" or "swo"', mode)

    @property
    def swo_div(self):
        """Set the number of trigger_clock cycles per SWO bit.

        Args:
            div (int): number of cycles per SWO bit.
        """
        return self.fpga_read(self.REG_SWO_BITRATE_DIV, 1)[0] + 1 # not a typo: hardware requires -1; doing this is easier than fixing the hardware

    @swo_div.setter
    def swo_div(self, div):
        if div < 1:
            raise ValueError
        return self.fpga_write(self.REG_SWO_BITRATE_DIV, [div-1]) # not a typo: hardware requires -1; doing this is easier than fixing the hardware

    @property
    def leds(self):
        """Set the meaning of the armed/capturing LEDs.

        Args:
            mode (str): "normal": as labeled (armed/capturing)
                        "hearbeat": armed = front-end clock heartbeat; capturing = trace clock heartbeat
        """
        if self.platform == 'CW305':
            return 'normal'
        else:
            raw = self.fpga_read(self.REG_LED_SELECT, 1)[0]
            if raw == 0:
                return 'normal'
            elif raw == 1:
                return 'hearbeat'
            else:
                raise ValueError

    @leds.setter
    def leds(self, mode):
        if mode == 'normal':
            val = 0
        elif mode == 'heartbeat':
            val = 1
        else:
            raise ValueError
        return self.fpga_write(self.REG_LED_SELECT, [val])


    @property
    def trace_width(self):
        """Set the parallel trace port width.

        Args:
            width (int): width of the trace port.
        """
        return self.fpga_read(self.REG_TRACE_WIDTH, 1)[0]

    @trace_width.setter
    def trace_width(self, width):
        if width not in [1,2,4]:
            raise ValueError("Unsupported trace width. Must be 1, 2 or 4.")
        if width != 4:
            tracewhisperer_logger.warning("Widths different than 4 may not work. Don't forget to set TPI_CSPSR properly.")
        return self.fpga_write(self.REG_TRACE_WIDTH, [width])

    def check_clocks(self):
        tracewhisperer_logger.warning('Deprecated, use trace.clock.trigger_locked instead.')
        return self.clock.trigger_locked

    def set_capture_mode(self, mode, counts=0):
        """Determine the duration of the trace capture.
        Args:
            mode (string): 'while_trig' or 'count_cycles' or 'count_writes'
            counts (int): number of cycles (mode == 'count_cycles') or writes (mode == 'count_writes') to capture for
                          (0 = capture until full)
        """
        tracewhisperer_logger.warning('Deprecated; use trace.capture.capture_mode / capture_count instead.')
        if mode == 'while_trig':
            self.fpga_write(self.REG_CAPTURE_WHILE_TRIG, [1])
        elif mode == 'count_cycles':
            self.fpga_write(self.REG_CAPTURE_WHILE_TRIG, [0])
            self.fpga_write(self.REG_COUNT_WRITES, [0])
            self.fpga_write(self.REG_CAPTURE_LEN, int.to_bytes(counts, length=4, byteorder='little'))
        elif mode == 'count_writes':
            self.fpga_write(self.REG_CAPTURE_WHILE_TRIG, [0])
            self.fpga_write(self.REG_COUNT_WRITES, [1])
            self.fpga_write(self.REG_CAPTURE_LEN, int.to_bytes(counts, length=4, byteorder='little'))
        else:
            tracewhisperer_logger.error('Invalid mode %s')


    @property
    def board_rev(self):
        """Obtain board revision from the FPGA bitfile.
        """
        return self.fpga_read(self.REG_BOARD_REV, 1)[0]


    def jtag_to_swd(self):
        """Switch to SWD mode by driving the JTAG-to-SWD sequence on TMS/TCK.
        (reference: https://developer.arm.com/documentation/ka001179/1-0/)
        Args: none
        """
        self.fpga_write(self.REG_USERIO_PWDRIVEN, [(1<<self.tms_bit) + (1<<self.tck_bit)])
        self.fpga_write(self.REG_USERIO_DATA, [1<<self.tms_bit])
        self._line_reset()
        self._send_tms_byte(0x9e)
        self._send_tms_byte(0xe7)
        self._line_reset()
        self.fpga_write(self.REG_USERIO_DATA, [1<<self.tms_bit])
        self.fpga_write(self.REG_USERIO_PWDRIVEN, [0])


    def _send_tms_byte(self, data):
        """Bit-bang 8 bits of data on TMS/TCK (LSB first).
        Args:
            data (int): 8 bits data to send.
        """
        for i in range(8):
            bit = (data & 2**i) >> i
            self.fpga_write(self.REG_USERIO_DATA, [bit<<self.tms_bit])
            self.fpga_write(self.REG_USERIO_DATA, [(1<<self.tck_bit) + (bit<<self.tms_bit)])


    def _line_reset(self, num_bytes=8):
        """Bit-bang a line reset on TMS/TCK.
        Args: none
        """
        for i in range(num_bytes): self._send_tms_byte(0xff)



    def simpleserial_write(self, cmd, data, printresult=False):
        """Convenience function to send a simpleserial command to the simpleserial target,
        and optionally fetch and print the result.
        """
        self._ss.simpleserial_write(cmd, data)
        if printresult:
            time.sleep(0.6) # ECC is slow!
            print(self._ss.read().split('\n')[0])


    def set_pattern_match(self, index, pattern, mask=[0xff]*8):
        """Sets pattern match and mask parameters

        Args:
            index: match index [0-7]
            pattern: list of 8-bit integers, pattern match value
            mask: list of 8-bit integers, pattern mask value

        """
        self.fpga_write(self.REG_TRACE_PATTERN0+index, pattern)
        self.fpga_write(self.REG_TRACE_MASK0+index, mask)
        # count trailing zeros in the mask, as these determine how much time elapses from
        # the start of receiving a trace packet, until the match is determined -- so that the
        # recorded timestamp can be rolled back to when the trace packet began
        trailing_zeros = 0
        for m in mask[::-1]:
            if not m:
                trailing_zeros += 1
        self.rule_length[index] = 8-trailing_zeros


    def arm_trace(self):
        """Arms trace sniffer for capture; also checks sync status.
        """
        assert self.trace_synced, 'Not synchronized!'
        self.fpga_write(self.REG_ARM, [1])


    @property
    def errors(self):
        """Indicate whether internal FPGA errors have occurred.
           Write to clear.
        """
        stat = ""
        if self.fpga_read(self.REG_STAT, 1)[0]:
            stat = "SWO internal CDC error, "
        fifo_stat = self.fpga_read(self.REG_SNIFF_FIFO_STAT, 1)[0]
        if (fifo_stat & 2) >> 1:
            stat += "FIFO underflow, "
        if (fifo_stat & 16) >> 4:
            stat += "FIFO overflow, "
        if stat:
            return stat
        else:
            return None

    @errors.setter
    def errors(self, val):
        self.fpga_write(self.REG_CLEAR_ERRORS, [1])


    @property
    def trace_synced(self):
        """Check whether the chosen front-end clock is alive, and, for 
           parallel trace mode, whether we are seeing valid sync frames.
        """
        if self.clock.fe_clock_alive and self.fpga_read(self.REG_SYNCHRONIZED, 1)[0] == 1:
            return True
        else:
            return False


    def resync(self):
        """Force trace sniffer to resynchronize (using sync frames that are
        continously emitted on the parallel trace port). Failure could be from
        absence of a trace clock, or mis-sampling of trace data due to
        setup/hold violations (clock edge too close to data edge).
        """
        self.fpga_write(self.REG_TRACE_RESET_SYNC, [1])
        assert self.trace_synced, 'Not synchronized!'


    def is_done(self):
        """Calls SimpleSerial target's is_done().
        """
        return self._ss.is_done()


    def fpga_write(self, addr, data):
        """Write to an FPGA register.

        Args:
            addr (int): Address to write to
            data (list): Data to write to addr
        """
        # on CW305, change word address to byte address (CW610 uses addressing differently)
        if self.platform == 'CW305':
            addr = addr << 7
        return self._naeusb.cmdWriteMem(addr, data)


    def fpga_read(self, addr, readlen=4):
        """Read from an FPGA register.

        Args:
            addr (int): Address to read from
            readlen (int): Length of data to read

        Returns:
            Requested data as a list
        """
        # on CW305, change word address to byte address (CW610 uses addressing differently)
        if self.platform == 'CW305':
            addr = addr << 7
        data = self._naeusb.cmdReadMem(addr, readlen)
        return data


    def check_fifo_errors(self, underflow=0, overflow=0):
        """Check whether an underflow or overflow occured on the capture FIFO.

        Args:
            underflow (int, optional): expected status, 0 or 1
            overflow (int, optional): expected status, 0 or 1
        """
        tracewhisperer_logger.warning('Deprecated; use trace.errors instead.')
        status = self.fpga_read(self.REG_SNIFF_FIFO_STAT, 1)[0]
        fifo_underflow = (status & 2) >> 1
        fifo_overflow = (status & 16) >> 4
        assert fifo_underflow == underflow
        assert fifo_overflow == overflow


    def fifo_empty(self):
        """Returns True if the capture FIFO is empty, False otherwise.
        """
        if self.fpga_read(self.REG_SNIFF_FIFO_STAT, 1)[0] & 1:
            return True
        else:
            return False


    @property
    def fpga_buildtime(self):
        """Returns date and time when FPGA bitfile was generated.
        """
        raw = self.fpga_read(addr=self.REG_BUILDTIME, readlen=4)
        # definitions: Xilinx XAPP1232
        day = raw[3] >> 3
        month = ((raw[3] & 0x7) << 1) + (raw[2] >> 7)
        year = ((raw[2] >> 1) & 0x3f) + 2000
        hour = ((raw[2] & 0x1) << 4) + (raw[1] >> 4)
        minute = ((raw[1] & 0xf) << 2) + (raw[0] >> 6)
        return "{}/{}/{}, {:02d}:{:02d}".format(month, day, year, hour, minute)

    def get_fpga_buildtime(self):
        tracewhisperer_logger.warning('Deprecated; use trace.fpga_buildtime instead.')
        return self.fpga_buildtime


    def get_fw_buildtime(self):
        """Returns date and time when target FW was compiled.
        """
        self._ss.simpleserial_write('i', b'')
        time.sleep(0.1)
        return self._ss.read().split('\n')[0]


    def phywhisperer_name(self):
        """Returns project-specific 'name' string embedded in PhyWhisperer bitfile
        """
        nameb = self.fpga_read(self.REG_NAME, 8)
        names = ''
        for i in nameb:
            names += hex(i)[2:]
        return bytearray.fromhex(names).decode()


    def test_itm(self, port=1):
        """Print test string via ITM using specified port number.

        Args:
            port (int): ITM port number to use.

        """
        self._ss.simpleserial_write('t', bytearray([port]))
        time.sleep(0.1)
        print(self._ss.read().split('\n')[0])


    def read_capture_data(self):
        """Read captured trace data.

        Returns: List of captured entries. Each list element is itself a 3-element list,
        containing the 3 bytes that make up a capture entry. Can be parsed by get_rule_match_times()
        or get_raw_trace_packets(). See defines_trace.v for definition of the FIFO
        data fields.

        """
        data = []
        starttime = time.time()

        # first check for FIFO to not be empty:
        assert self.fifo_empty() == False, 'FIFO is empty'

        # then check that no underflows or overflows occurred during capture:
        assert self.errors is None

        while not self.fifo_empty():
            data.append(self.fpga_read(self.REG_SNIFF_FIFO_RD, 4)[1:4])

        if len(data): # maybe we only got empty reads
            if data[-1][2] & 2**self.FE_FIFO_STAT_UNDERFLOW:
                logging.warning("Capture FIFO underflowed!")

        return data


    def print_raw_data(self, rawdata):
        """Prints collected raw data in hexadecimal. Raw data includes data
        type, timestamp, and payload. See defines_trace.v for bitfield
        definitions.
        """
        for e in rawdata:
            entry = 0
            entry += (e[2] & 0x3) << 16
            entry += e[1] << 8
            entry += e[0]
            print('%05x' % entry)


    def get_rule_match_times(self, rawdata, rawtimes=False, verbose=False):
        """Split raw capture data into data events and times, stat events and times.

        Args:
            rawdata: raw capture data, list of lists, e.g. obtained from read_capture_data()
            rawtimes:
                True: return reported times (obtained at the *end* of the pattern match)
                False: roll back times to the *start* of the pattern match
            verbose: print timestamped rules
        Returns:
            list of [time, rule index] tuples
        """

        times = []
        timecounter = 0
        lasttime = 0
        lastadjust = 0
        for raw in rawdata:
            command = raw[2] & 0x3
            if command == self.FE_FIFO_CMD_DATA:
                timecounter += raw[0]
                data = raw[1]
                rule = int(math.log2(data))
                if rawtimes:
                    adjust = 0
                else:
                    adjust = self.rule_length[rule]*self._cycles_per_byte()
                timecounter = timecounter - adjust + lastadjust
                delta = timecounter - lasttime
                lasttime = timecounter
                lastadjust = adjust
                if verbose:
                    print("%8d rule # %d, delta = %d" % (timecounter, rule, delta))
                times.append([timecounter, rule])
            elif command == self.FE_FIFO_CMD_TIME:
                timecounter += raw[0] + (raw[1] << 8)
            elif command == self.FE_FIFO_CMD_STAT:
                raise ValueError("Unexpected STAT command, not supported by this method; maybe try get_raw_trace_packets() instead?")
            elif command == self.FE_FIFO_CMD_STRM:
                pass
        return times


    def _cycles_per_byte(self):
        """Returns number of clock cycles needed to send one byte of trace
        data over the trace or SWO port.
        """
        if self.swo_mode:
            return 8
        else:
            return 8/self._trace_port_width


    def get_raw_trace_packets(self, rawdata, removesyncs=True, verbose=False):
        """Split raw capture data into pseudo-frames, optionally suppressing
        sync frames (and using those sync frames as marker which is separating
        pseudo-frames). It's the best we can do without actually parsing the
        trace packets, which is best left to other tools!

        Args:
            rawdata: raw capture data, list of lists, e.g. obtained from read_capture_data()
            verbose: print timestamped packets
        Returns:
            list of pseudo-frames
        """

        pseudoframes = []
        pseudoframe = []
        timecounter = 0
        lasttime = 0
        for raw in rawdata:
            command = raw[2] & 0x3
            if command == self.FE_FIFO_CMD_STAT:
                timecounter += raw[0]
                data = raw[1]
                if not len(pseudoframe):
                    starttime = timecounter
                pseudoframe.append(data)

                if removesyncs:
                    if pseudoframe[-len(self.longsync):] == self.longsync:
                        pseudoframe = pseudoframe[:-len(self.longsync)]
                        sync_removed = True
                        #print('Removed long')
                    elif pseudoframe[-len(self.shortsync):] == self.shortsync:
                        pseudoframe = pseudoframe[:-len(self.shortsync)]
                        sync_removed = True
                        #print('Removed short')
                    else:
                        sync_removed = False
                else:
                    sync_removed = False

                if sync_removed and len(pseudoframe):
                    pseudoframes.append([starttime, pseudoframe])
                    if verbose:
                        print("Pseudoframe: ", end='')
                        for b in pseudoframe:
                            print('%02x ' % b, end='')
                        print();
                    pseudoframe = []

                delta = timecounter - lasttime
                lasttime = timecounter

            elif command == self.FE_FIFO_CMD_TIME:
                timecounter += raw[0] + (raw[1] << 8)
            elif command == self.FE_FIFO_CMD_DATA:
                raise ValueError("Unexpected DATA command, not supported by this method; maybe try get_rule_match_times() instead?")
            elif command == self.FE_FIFO_CMD_STRM:
                pass

        if not removesyncs:
            pseudoframes.append([starttime, pseudoframe])

        return pseudoframes



    def use_soft_trigger(self):
        """ Use target-generated trigger to initiate trace capture.
        """
        tracewhisperer_logger.warning('Deprecated; use trace.capture.trigger_source instead.')
        self.fpga_write(self.REG_SOFT_TRIG_ENABLE, [1])
        self.fpga_write(self.REG_SOFT_TRIG_PASSTHRU, [1])
        self.fpga_write(self.REG_PATTERN_TRIG_ENABLE, [0])


    def use_trace_trigger(self, rule=0):
        """ Use matching trace data to initiate trace capture.
        Args:
            rule (int): rule number to use
        """
        tracewhisperer_logger.warning('Deprecated; use trace.capture.trigger_source instead.')
        self.fpga_write(self.REG_SOFT_TRIG_ENABLE, [0])
        self.fpga_write(self.REG_SOFT_TRIG_PASSTHRU, [0])
        self.fpga_write(self.REG_PATTERN_TRIG_ENABLE, [2**rule])
        self.fpga_write(self.REG_TRIGGER_ENABLE, [1])
        # these can be customized but let's start you off with simple default values:
        self.fpga_write(self.REG_NUM_TRIGGERS, [1])
        self.fpga_write(self.REG_TRIGGER_WIDTH, [16])


    def set_isync_matches(self, addr0=0, addr1=0, match=None):
        """ Set exact PC address matching rules.
        Args:
            addr0 (int): Matching address 0 (DWT_COMP0)
            addr1 (int): Matching address 0 (DWT_COMP1)
            match:
                None: disable PC address match packets
                0: enable addr0 matching only
                1: enable addr1 matching only
                "both": enable both addr0 and addr1 matching
        """
        self.target_registers.DWT_COMP0 = addr0
        self.target_registers.DWT_COMP1 = addr1
        if match == None:
            self.target_registers.ETM_TEEVR = '00000000'
        elif match == 0:
            self.target_registers.ETM_TEEVR = '00000020'
        elif match == 1:
            self.target_registers.ETM_TEEVR = '00000021'
        elif match == 'both':
            self.target_registers.ETM_TEEVR = '000150a0'


    def set_periodic_pc_sampling(self, enable=1, cyctap=0, postinit=1, postreset=0):
        """ Set periodic PC sampling parameters. Enabling PC sampling through
        this method will start PC sampling *after* the target triggers, thereby
        ensuring that the resulting trace data can be parsed without trouble.
        Alternatively, you can set the DWT_CTRL register directly.
        Args:
            enable (int): enable or disable periodic PC sampling
            cyctap (int): DWT_CTRL.CYCTAP bit
            postinit (int): DWT_CTRL.POSTINIT bits
            postreset (int): DWT_CTRL.POSTRESET bits
        """
        self.target_registers.cached_values[self.target_registers.regs['DWT_CTRL']] = None # this may change DTW_CTRL, so uncache it
        self.simpleserial_write('c', bytearray([enable, cyctap, postinit, postreset]), printresult=False)


    def write_raw_capture(self, raw, filename='raw.bin', presyncs=8):
        """Writes raw trace data to a file (which can be read by orbuculum).
        Prepends a number of sync frames to facilitate parsing.
        Args:
            raw (array): raw trace data as obtained from
                get_raw_trace_packets()
            filename (string): output file
            presyncs (int): number of long syncronization frames which are
                prepended to the collected trace data.
        """
        binout = open(filename, "wb")
        for i in range(presyncs):
            binout.write(bytes(self.longsync))
        for frame in raw:
            binout.write(bytes(frame[1]))
        binout.close()



class clock(util.DisableNewAttr):
    ''' Clock-related settings.
    '''
    _name = 'TraceWhisperer clock settings'

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.drp = XilinxDRP(main, main.REG_TRIGGER_DRP_DATA, main.REG_TRIGGER_DRP_ADDR, main.REG_TRIGGER_DRP_RESET)
        self.mmcm = XilinxMMCMDRP(self.drp)
        self.disable_newattr()

    def _dict_repr(self):
        rtn = OrderedDict()
        rtn['fe_clock_alive']   = self.fe_clock_alive
        if self.main.platform == 'CW610':
            rtn['fe_clock_src']     = self.fe_clock_src
        rtn['fe_freq']          = self.fe_freq
        rtn['trigger_locked']   = self.trigger_locked
        rtn['trigger_freq']     = self.trigger_freq
        return rtn

    def __repr__(self):
        return util.dict_to_str(self._dict_repr())

    def __str__(self):
        return self.__repr__()

    @property
    def fe_freq(self):
        """Measured clock frequency of the selected front-end clock, as set by trace.clock.fe_clock_src.
        """
        raw = int.from_bytes(self.main.fpga_read(self.main.REG_FE_FREQ, 4), byteorder='little')
        freq = raw * 96e6 / float(pow(2,23))
        return freq

    @property
    def trigger_freq(self):
        """Measured clock frequency of the trigger clock, which is used for both (a) trigger generation
           and (b) SWO sampling.
        """
        raw = int.from_bytes(self.main.fpga_read(self.main.REG_TRIGGER_FREQ, 4), byteorder='little')
        freq = raw * 96e6 / float(pow(2,23))
        return freq

    @trigger_freq.setter
    def trigger_freq(self, freq, vcomin=600e6, vcomax=1200e6):
        """Calculate Multiply & Divide settings based on input frequency"""
        if not self.fe_clock_alive:
            raise ValueError("FE clock not present, cannot calculate proper M/D settings")
        input_freq = self.fe_freq
        lowerror = 1e99
        best = (0,0,0)
        for maindiv in range(1,6):
            mmin = int(np.ceil(vcomin/input_freq*maindiv))
            mmax = int(np.ceil(vcomax/input_freq*maindiv))
            for mul in range(mmin,mmax+1):
                if mul/maindiv < vcomin/input_freq or mul/maindiv > vcomax/input_freq or mul >= 2**7:
                    continue
                for secdiv in range(1,127):
                    calcfreq = input_freq*mul/maindiv/secdiv
                    err = abs(freq - calcfreq)
                    if err < lowerror:
                        lowerror = err
                        best = (mul, maindiv, secdiv)
        if best == (0,0,0):
            raise ValueError("Couldn't find a legal div/mul combination")
        self.mmcm.set_mul(best[0])
        self.mmcm.set_main_div(best[1])
        self.mmcm.set_sec_div(best[2])

    @property
    def fe_clock_alive(self):
        """Indicates whether the selected front-end clock appears to be alive.
        """
        read1 = int.from_bytes(self.main.fpga_read(self.main.REG_FE_CLOCK_COUNT, 4), byteorder='little')
        read2 = int.from_bytes(self.main.fpga_read(self.main.REG_FE_CLOCK_COUNT, 4), byteorder='little')
        if read1 == read2:
            return False
        else:
            return True

    @property 
    def trigger_locked(self):
        """Indicates whether the FPGA MMCM which generates the trigger clock is locked.
        """
        if self.main.fpga_read(self.main.REG_MMCM_LOCKED, 1)[0] & 2:
            return True
        else:
            return False

    @property
    def fe_clock_src(self):
        """Choose which clock is used as the front-end clock.
        Args:
            src (str): "target_clock", "trace_clock" or "usb_clock"
        """
        if self.main.platform == 'CW305':
            return 'target_clock'
        else:
            raw = self.main.fpga_read(self.main.REG_FE_CLOCK_SEL, 1)[0]
            if raw == 0:
                return 'target_clock'
            elif raw == 1:
                return 'trace_clock'
            elif raw == 2:
                return 'usb_clock'
            else:
                raise ValueError("Unexpected value: %d" % raw)

    @fe_clock_src.setter
    def fe_clock_src(self, src):
        if src == 'target_clock':
            val = 0
        elif src == 'trace_clock':
            val = 1
        elif src == 'usb_clock':
            val = 2
        else:
            raise ValueError
        self.main.fpga_write(self.main.REG_FE_CLOCK_SEL, [val])



class capture(util.DisableNewAttr):
    ''' Capture-related settings.
    '''
    _name = 'TraceWhisperer capture settings'

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.disable_newattr()

    def _dict_repr(self):
        rtn = OrderedDict()
        rtn['trigger_source']           = self.trigger_source
        rtn['raw']                      = self.raw
        rtn['rules_enabled']            = self.rules_enabled
        rtn['mode']                     = self.mode
        rtn['count']                    = self.count
        rtn['record_syncs']             = self.record_syncs
        rtn['matched_pattern_data']     = self.matched_pattern_data
        rtn['matched_pattern_counts']   = self.matched_pattern_counts
        return rtn

    def __repr__(self):
        return util.dict_to_str(self._dict_repr())

    def __str__(self):
        return self.__repr__()

    @property
    def raw(self):
        """ Set whether TraceWhisperer captures raw trace data or matching rule indices.
        Args:
            val (int or bool): if set, capture raw trace data. Otherwise, capture the index
                               of the matching rule number.
        """
        if self.main.fpga_read(self.main.REG_CAPTURE_RAW, 1)[0]:
            return True
        else:
            return False

    @raw.setter
    def raw(self, val):
        if val:
            self.main.fpga_write(self.main.REG_CAPTURE_RAW, [1])
        else:
            self.main.fpga_write(self.main.REG_CAPTURE_RAW, [0])

    @property
    def record_syncs(self):
        """ Set whether TraceWhisperer captures all trace sync frames or not.
            Note: since the TraceWhisperer FPGA does not parse the ETM frames,
            this is done as "best effort", and some sync frames will still be
            captured. The intent of this feature is to minimize the storage
            consumed by the sync frames, not eliminate it.
        Args:
            val (int or bool)
        """
        if self.main.fpga_read(self.main.REG_RECORD_SYNCS, 1)[0]:
            return True
        else:
            return False

    @record_syncs.setter
    def record_syncs(self, val):
        if val:
            self.main.fpga_write(self.main.REG_RECORD_SYNCS, [1])
        else:
            self.main.fpga_write(self.main.REG_RECORD_SYNCS, [0])

    @property
    def matched_pattern_data(self):
        """ Return the actual trace data seen for the last matched pattern.
        """
        return '%016x' % (int.from_bytes(self.main.fpga_read(self.main.REG_MATCHED_DATA, 8)[::-1], byteorder='little'))

    @property
    def matched_pattern_counts(self):
        """ Return a list with the number of times each pattern match rule was matched.
        """
        return list(self.main.fpga_read(self.main.REG_TRACE_COUNT, 8)[::-1])


    @property
    def trigger_source(self):
        """ Set whether firmware trigger or trace trigger is used to enable recording of trace data.
        Args:
            source (str or int): "firmware trigger": Use target-generated trigger to initiate trace capture.
                                 int: use matching trace data to initiate trace capture, with given rule number.
        """
        if self.main.fpga_read(self.main.REG_SOFT_TRIG_ENABLE, 1)[0]:
            return('firmware trigger')
        else:
            raw = self.main.fpga_read(self.main.REG_PATTERN_TRIG_ENABLE, 1)[0]
            if raw > 0:
                return('trace trigger, rule #%d' % int(math.log2(raw)))
            else:
                return('trace trigger (no rule set)')

    @trigger_source.setter
    def trigger_source(self, source):
        if source == 'firmware trigger':
            self.main.fpga_write(self.main.REG_SOFT_TRIG_ENABLE, [1])
            self.main.fpga_write(self.main.REG_SOFT_TRIG_PASSTHRU, [1])
            self.main.fpga_write(self.main.REG_PATTERN_TRIG_ENABLE, [0])
        else:
            if type(source) == int:
                self.main.fpga_write(self.main.REG_SOFT_TRIG_ENABLE, [0])
                self.main.fpga_write(self.main.REG_SOFT_TRIG_PASSTHRU, [0])
                self.main.fpga_write(self.main.REG_PATTERN_TRIG_ENABLE, [2**source])
                self.main.fpga_write(self.main.REG_TRIGGER_ENABLE, [1])
                # these can be customized but let's start you off with simple default values:
                self.main.fpga_write(self.main.REG_NUM_TRIGGERS, [1])
                self.main.fpga_write(self.main.REG_TRIGGER_WIDTH, [16])
            else:
                raise TypeError

    @property
    def mode(self):
        """Determine the duration of the trace capture.
        Args:
            mode (string): 'while_trig': capture while the trigger input is high
                           'count_cycles': capture for self.count clock cycles
                           'count_writes': capture self.count events
        """
        raw = self.main.fpga_read(self.main.REG_CAPTURE_WHILE_TRIG, 1)[0]
        if raw:
            return "while_trig"
        else:
            raw = self.main.fpga_read(self.main.REG_COUNT_WRITES, 1)[0]
            if raw:
                return "count_writes"
            else:
                return "count_cycles"

    @mode.setter
    def mode(self, mode):
        if mode == 'while_trig':
            self.main.fpga_write(self.main.REG_CAPTURE_WHILE_TRIG, [1])
        elif mode == 'count_cycles':
            self.main.fpga_write(self.main.REG_CAPTURE_WHILE_TRIG, [0])
            self.main.fpga_write(self.main.REG_COUNT_WRITES, [0])
        elif mode == 'count_writes':
            self.main.fpga_write(self.main.REG_CAPTURE_WHILE_TRIG, [0])
            self.main.fpga_write(self.main.REG_COUNT_WRITES, [1])
        else:
            tracewhisperer_logger.error('Invalid mode %s')

    @property
    def count(self):
        """Control how long we capture trace events when self.mode != 'while_trig'.
        Args:
            counts (int): number of clock cycles (self.mode == 'count_cycles') or writes 
                          (self.mode == 'count_writes') to capture for; 0 means capture until
                          storage is full
        """
        return int.from_bytes(self.main.fpga_read(self.main.REG_CAPTURE_LEN, 4), byteorder='little')

    @count.setter
    def count(self, counts):
        self.main.fpga_write(self.main.REG_CAPTURE_LEN, int.to_bytes(counts, length=4, byteorder='little'))

    @property
    def rules_enabled(self):
        """Set which matching rules are enabled.
        Args:
            rules (list of ints): turn on the specified rules; others are turned off.
                                  example: [0, 5, 7]: turns on rules 0, 5 and 7.
        """
        raw = self.main.fpga_read(self.main.REG_PATTERN_ENABLE, 1)[0]
        rules = []
        for b in range(8):
            if raw & 2**b:
                rules.append(b)
        return rules

    @rules_enabled.setter
    def rules_enabled(self, rules):
        raw = 0
        for rule in rules:
            raw += 2**rule
        self.main.fpga_write(self.main.REG_PATTERN_ENABLE, [raw])



class ARM_debug_registers(util.DisableNewAttr):
    ''' Convenience methods to set or get ARM debug registers (requires firmware support).
    '''
    _name = 'ARM target debug registers for TraceWhisperer'

    # must be in sync with target firmware:
    regs = {
            'DWT_CTRL':     0x0,
            'DWT_COMP0':    0x1,
            'DWT_COMP1':    0x2,
            'ETM_CR':       0x3,
            'ETM_TESSEICR': 0x4,
            'ETM_TEEVR':    0x5,
            'ETM_TECR1':    0x6,
            'ETM_TRACEIDR': 0x7,
            'TPI_ACPR':     0x8,
            'TPI_SPPR':     0x9,
            'TPI_FFCR':     0xa,
            'TPI_CSPSR':    0xb,
            'ITM_TCR':      0xc
           }

    def __init__(self, serial):
        super().__init__()
        # oaiface = OpenADCInterface
        self._ss = serial
        self.cached_values = [None] * len(self.regs)
        self.disable_newattr()

    def _dict_repr(self):
        rtn = OrderedDict()
        rtn['DWT_CTRL']     = self.DWT_CTRL
        rtn['DWT_COMP0']    = self.DWT_COMP0
        rtn['DWT_COMP1']    = self.DWT_COMP1
        rtn['ETM_CR']       = self.ETM_CR
        rtn['ETM_TESSEICR'] = self.ETM_TESSEICR
        rtn['ETM_TEEVR']    = self.ETM_TEEVR
        rtn['ETM_TECR1']    = self.ETM_TECR1
        rtn['ETM_TRACEIDR'] = self.ETM_TRACEIDR
        rtn['TPI_ACPR']     = self.TPI_ACPR
        rtn['TPI_SPPR']     = self.TPI_SPPR
        rtn['TPI_FFCR']     = self.TPI_FFCR
        rtn['TPI_CSPSR']    = self.TPI_CSPSR
        rtn['ITM_TCR']      = self.ITM_TCR

        return rtn

    def __repr__(self):
        return util.dict_to_str(self._dict_repr())

    def __str__(self):
        return self.__repr__()

    @property 
    def DWT_CTRL(self):
        return self._get('DWT_CTRL')

    @DWT_CTRL.setter
    def DWT_CTRL(self, val): 
        self._set('DWT_CTRL', val)

    @property
    def DWT_COMP0(self):
        return self._get('DWT_COMP0')

    @DWT_COMP0.setter
    def DWT_COMP0(self, val): 
        self._set('DWT_COMP0', val)

    @property
    def DWT_COMP1(self): 
        return self._get('DWT_COMP1')

    @DWT_COMP1.setter
    def DWT_COMP1(self, val): 
        self._set('DWT_COMP1', val)

    @property
    def ETM_CR(self): 
        return self._get('ETM_CR')

    @ETM_CR.setter
    def ETM_CR(self, val): 
        self._set('ETM_CR', val)

    @property
    def ETM_TESSEICR(self): 
        return self._get('ETM_TESSEICR')

    @ETM_TESSEICR.setter
    def ETM_TESSEICR(self, val): 
        self._set('ETM_TESSEICR', val)

    @property
    def ETM_TEEVR(self): 
        return self._get('ETM_TEEVR')

    @ETM_TEEVR.setter
    def ETM_TEEVR(self, val): 
        self._set('ETM_TEEVR', val)

    @property
    def ETM_TECR1(self): 
        return self._get('ETM_TECR1')

    @ETM_TECR1.setter
    def ETM_TECR1(self, val): 
        self._set('ETM_TECR1', val)

    @property
    def ETM_TRACEIDR(self): 
        return self._get('ETM_TRACEIDR')

    @ETM_TRACEIDR.setter
    def ETM_TRACEIDR(self, val): 
        self._set('ETM_TRACEIDR', val)

    @property
    def TPI_ACPR(self): 
        return self._get('TPI_ACPR')

    @TPI_ACPR.setter
    def TPI_ACPR(self, val): 
        self._set('TPI_ACPR', val)

    @property
    def TPI_SPPR(self): 
        return self._get('TPI_SPPR')

    @TPI_SPPR.setter
    def TPI_SPPR(self, val): 
        self._set('TPI_SPPR', val)

    @property
    def TPI_FFCR(self): 
        return self._get('TPI_FFCR')

    @TPI_FFCR.setter
    def TPI_FFCR(self, val): 
        self._set('TPI_FFCR', val)

    @property
    def TPI_CSPSR(self): 
        return self._get('TPI_CSPSR')

    @TPI_CSPSR.setter
    def TPI_CSPSR(self, val): 
        self._set('TPI_CSPSR', val)

    @property
    def ITM_TCR(self): 
        return self._get('ITM_TCR')

    @ITM_TCR.setter
    def ITM_TCR(self, val): 
        self._set('ITM_TCR', val)

    def _set(self, reg, data, printresult=False):
        """Set a Cortex debug register
        Args:
            reg (string): Register to write. See self.regs for available registers.
            data (int or string): 32-bit integer or 8-character hex string, value to write to
                                  specified register (e.g. '1000F004')
        """
        if reg in self.regs:
            if type(data) == str:
                data_str = data
                data_int = int(data, 16)
            elif type(data) == int:
                data_str = '%08x' % data
                data_int = data
            else:
                raise TypeError

            self.cached_values[self.regs[reg]] = data_int
            data = '%02x' % self.regs[reg] + data_str
            self._ss.simpleserial_write('s', util.hexStrToByteArray(data))
            time.sleep(0.1)
            if printresult:
                print(self._ss.read().split('\n')[0])
        else:
            tracewhisperer_logger.error('Register %s does not exist.', reg)


    def _get(self, reg):
        """Reads a Cortex debug register
        Args:
            reg (string): Register to read. See self.regs for available registers.
        """
        if reg in self.regs:
            if self.cached_values[self.regs[reg]]:
                val = self.cached_values[self.regs[reg]]
            else:
                data = '%02x' % self.regs[reg] + '00000000'
                self._ss.simpleserial_write('g', util.hexStrToByteArray(data))
                time.sleep(0.1)
                val = int(self._ss.read().split('\n')[0][1:], 16)
                self.cached_values[self.regs[reg]] = val
            return '%08x' % val
        else:
            tracewhisperer_logger.error('Register %s does not exist.', reg)


