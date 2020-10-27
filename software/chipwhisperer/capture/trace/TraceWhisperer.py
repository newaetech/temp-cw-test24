#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2020, NewAE Technology Inc
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
import logging
import time
import re
import math
import pkg_resources
import chipwhisperer as cw
from chipwhisperer.common.utils import util
from chipwhisperer.common.traces import Trace
from chipwhisperer.hardware.naeusb.naeusb import NAEUSB
from chipwhisperer.hardware.naeusb.fpga import FPGA

class TraceWhisperer():

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

    # must be in sync with firmware:
    regs = {
            'DWT_CTRL':     '00',
            'DWT_COMP0':    '01',
            'DWT_COMP1':    '02',
            'ETM_CR':       '03',
            'ETM_TESSEICR': '04',
            'ETM_TEEVR':    '05',
            'ETM_TECR1':    '06',
            'ETM_TRACEIDR': '07',
            'TPI_ACPR':     '08',
            'TPI_SPPR':     '09',
            'TPI_FFCR':     '0a',
            'TPI_CSPSR':    '0b',
            'ITM_TCR':      '0c'
           }

    rule_length = [0]*8

    longsync = [255, 255, 255, 127]
    shortsync = [255, 127]

    def __init__(self, target, scope=None, defines_files=None, bs='', force_bitfile=False):
        """
        Args:
            target: SimpleSerial target
            naeusb: NewAE USB interface
            platform (string): CW305 or CW610 (PhyWhisperer)
            defines_files (list of 2 strings): path to defines_trace.v and defines_pw.v
        """
        super().__init__()
        self._trace_port_width = 4
        # Detect whether we exist on CW305 or CW610 based on the target we're given:
        if target._name == 'Simple Serial':
            self.platform = 'CW610'
            self._ss = target
            self._naeusb = NAEUSB()
            self._naeusb.con(idProduct=[0xC610])
            # we're using the CW NAEUSB, which has no knowledge of PW firmware, so let's manually
            # check the FW version here:
            fw_latest = [1,1]
            if self._naeusb.readFwVersion()[0] < fw_latest[0]:
               logging.warning('Your PhyWhisperer firmware is outdated - latest is %d.%d' % (fw_latest[0], fw_latest[1]) +
                               '. Suggested to update firmware, as you may experience errors.')
 
            self._fpga = FPGA(self._naeusb)
            if not self._fpga.isFPGAProgrammed() or force_bitfile:
                if not bs:
                    bs = pkg_resources.resource_filename('chipwhisperer', 'hardware/firmware/tracewhisperer_top.bit')
                self._fpga.FPGAProgram(open(bs, 'rb'), exceptOnDoneFailure=False)
        else:
            self.platform = 'CW305'
            self._ss = cw.target(scope)
            self._naeusb = target._naeusb

        self.slurp_defines(defines_files)


    def reset_fpga(self):
        """ Reset FPGA registers to defaults, use liberally to clear incorrect states (CW610 only).
        """
        if self.platform == 'CW610':
            self._fpga.sendCtrl(0x25, 0x00)
        else:
            logging.error('reset_fpga() is only supported on CW610 platform')


    def slurp_defines(self, defines_files=None):
        """ Parse Verilog defines file so we can access register and bit
        definitions by name and avoid 'magic numbers'.
        """
        self.verilog_define_matches = 0
        if not defines_files:
            #defines_files = ['../hardware/CW305_DesignStart/hdl/defines_trace.v',
            #                 '../hardware/phywhisperer/software/phywhisperer/firmware/defines_pw.v']
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
                            logging.warning("Couldn't parse line: %s", define)
            defines.close()
        # make sure everything is cool:
        assert self.verilog_define_matches == 96, "Trouble parsing Verilog defines file (%s): didn't find the right number of defines; expected 96, got %d" % (defines_file, self.verilog_define_matches)


    def simpleserial_write(self, cmd, data, printresult=False):
        """Convenience function to send a simpleserial command to the simpleserial target,
        and optionally fetch and print the result.
        """
        self._ss.simpleserial_write(cmd, data)
        if printresult:
            time.sleep(0.6) # ECC is slow!
            print(self._ss.read().split('\n')[0])


    def set_reg(self, reg, data, printresult=False):
        """Set a Cortex debug register
        Args:
            reg (string): Register to write. See self.regs for available registers.
            data (string): 8-character hex string, value to write to COMP0 (e.g. '1000F004')
        """
        if reg in self.regs:
            data = self.regs[reg] + data
            self._ss.simpleserial_write('s', util.hexStrToByteArray(data))
            time.sleep(0.1)
            if printresult:
                print(self._ss.read().split('\n')[0])
        else:
            logging.error('Register %s does not exist.', reg)


    def get_reg(self, reg):
        """Reads a Cortex debug register
        Args:
            reg (string): Register to read. See self.regs for available registers.
        """
        if reg in self.regs:
            data = self.regs[reg] + '00000000'
            self._ss.simpleserial_write('g', util.hexStrToByteArray(data))
            time.sleep(0.1)
            return self._ss.read().split('\n')[0][1:]
        else:
            logging.error('Register %s does not exist.', reg)


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
        """Arms trace sniffer for capture.
        """
        self.fpga_write(self.REG_ARM, [1])


    def synced(self):
        """Checks that trace trigger module is synchronized.
        """
        assert self.fpga_read(self.REG_SYNCHRONIZED, 1)[0] == 1, 'Not synchronized!'


    def resync(self):
        """Force trace sniffer to resynchronize (using sync frames that are
        continously emitted on the parallel trace port). Failure could be from
        absence of a trace clock, or mis-sampling of trace data due to
        setup/hold violations (clock edge too close to data edge).
        """
        self.fpga_write(self.REG_TRACE_RESET_SYNC, [1])
        self.fpga_write(self.REG_TRACE_RESET_SYNC, [0])
        self.synced()


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


    def get_fpga_buildtime(self):
        """Returns date and time when FPGA bitfile was generated.
        """
        raw = self.fpga_read(addr=self.REG_BUILDTIME, readlen=4)
        # definitions: Xilinx XAPP1232
        day = raw[3] >> 3
        month = ((raw[3] & 0x7) << 1) + (raw[2] >> 7)
        year = ((raw[2] >> 1) & 0x3f) + 2000
        hour = ((raw[2] & 0x1) << 4) + (raw[1] >> 4)
        minute = ((raw[1] & 0xf) << 2) + (raw[0] >> 6)
        return "FPGA build time: {}/{}/{}, {}:{}".format(month, day, year, hour, minute)


    def get_fw_buildtime(self):
        """Returns date and time when target FW was compiled.
        """
        self._ss.simpleserial_write('i', b'')
        time.sleep(0.1)
        print(self._ss.read().split('\n')[0])


    def get_target_name(self):
        """Returns project-specific 'name' embedded in target bitfile
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
        self.check_fifo_errors()

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
                True: return reported times. 
                False: roll back times to when matching trace packets started coming out
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
                #hardware reports the number of cycles between events, so to
                #obtain elapsed time we add one:
                timecounter += raw[0] + 1
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
                    print("%8d rule # %d, delta = %d, adjust = %d" % (timecounter, rule, delta, adjust))
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
        data over the trace port.
        """
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
                #hardware reports the number of cycles between events, so to
                #obtain elapsed time we add one:
                timecounter += raw[0] + 1
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
        self.fpga_write(self.REG_SOFT_TRIG_ENABLE, [1])
        self.fpga_write(self.REG_SOFT_TRIG_PASSTHRU, [1])
        self.fpga_write(self.REG_PATTERN_TRIG_ENABLE, [0])


    def use_trace_trigger(self, rule=0):
        """ Use matching trace data to initiate trace capture.
        Args:
            rule (int): rule number to use
        """
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
        self.set_reg('DWT_COMP0', '%08x' % addr0)
        self.set_reg('DWT_COMP1', '%08x' % addr1)
        if match == None:
            self.set_reg('ETM_TEEVR', '00000000')
        elif match == 0:
            self.set_reg('ETM_TEEVR', '00000020')
        elif match == 1:
            self.set_reg('ETM_TEEVR', '00000021')
        elif match == 'both':
            self.set_reg('ETM_TEEVR', '000150a0')


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


