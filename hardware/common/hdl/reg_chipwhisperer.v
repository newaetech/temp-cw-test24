`include "includes.v"
//`define CHIPSCOPE

/***********************************************************************
This file is part of the ChipWhisperer Project. See www.newae.com for more
details, or the codebase at http://www.chipwhisperer.com

Copyright (c) 2014, NewAE Technology Inc. All rights reserved.
Author: Colin O'Flynn <coflynn@newae.com>

  chipwhisperer is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.

  chipwhisperer is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU Lesser General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with chipwhisperer.  If not, see <http://www.gnu.org/licenses/>.
*************************************************************************/
module reg_chipwhisperer(
	input 			reset_i,
	input 			clk,
	input [5:0]    reg_address,  // Address of register
	input [15:0]   reg_bytecnt,  // Current byte count
	input [7:0]    reg_datai,    // Data to write
	inout [7:0]    reg_datao,    // Data to read
	input [15:0]   reg_size,     // Total size being read/write
	input          reg_read,     // Read flag
	input  			reg_write,    // Write flag
	input          reg_addrvalid,// Address valid flag
	output			reg_stream,	
	
	input [5:0]    reg_hypaddress,
	output  [15:0] reg_hyplen,
	
	/* External Clock */
	inout				extclk_fpa_io,
	input				extclk_fpb_i,
	input				extclk_pll_i,
	input				extclk_rearin_i,
	output			extclk_rearout_o,
	output			extclk_o,
			
	/* Extern Trigger Connections */
	input 			adc_sample_clk,
	inout				trigger_fpa_i,
	inout				trigger_fpb_i,
	input				trigger_io1_i,
	input				trigger_io2_i,
	input				trigger_io3_i,
	input				trigger_io4_i,
	
	/* Advanced IO Trigger Connections */
	output			trigger_ext_o,	
	input				trigger_advio_i, 
	input				trigger_anapattern_i,
	
	/* Clock Sources */
	input				clkgen_i,
	input				glitchclk_i,
	
	/* GPIO Pins & Routing */
	inout				targetio1_io,
	inout				targetio2_io,
	inout				targetio3_io,
	inout				targetio4_io,
	
	output			hsglitch_o,
	
	input				uart_tx_i,
	output			uart_rx_o,
	
	input				usi_out_i,
	output			usi_in_o,
	
	/* Main trigger connections */
	output			trigger_o /* Trigger signal to capture system */
    ); 
	 wire	  reset;
	 assign reset = reset_i;
    
	 `define CW_EXTCLK_ADDR			38
	 `define CW_TRIGSRC_ADDR		39
	 `define CW_TRIGMOD_ADDR		40
	 `define CW_IOROUTE_ADDR      55
 
 /*  0xXX - External Clock Connections (One Byte)
	 
	   [  G RO RO FA FA S  S  S ]
	     
		  S S S = 000 Front Panel Channel A
					 001 Front Panel Channel B
					 010 Front Panel PLL Input
		          011 Rear TargetIO - High Speed Input
					 100 Rear TargetIO - High Speed Output				
					
			FA = 00 Front Panel A: High-Z (REQUIRED if using as input)
			     01 Front Panel A: CLKGEN
				  10 Front Panel A: Glitch Module	
					
			RO = (Bit 6/Bit 5) Rear Clock Out Source
       		  00 : Disabled (constant)
				  10 : CLKGEN
				  11 : Glitch Module
				  
			G  = (Bit 7) Glitch Output
			     0  : Disabled
				  1  : Glitch Module
   
     0xXX - External Trigger Connections (One Byte)
	 
	   [  M  M  R4  R3  R2  R1  FB FA ]
	     All external triggers are combined into a single
		  trigger signal, which can then be passed into one
		  of the enabled 'trigger modules'
		  
		  FA = Front Panel Channel A
		  FB = Front Panel Channel B
		  R1 = Rear TargetIO - Line 1
		  R2 = Rear TargetIO - Line 2
		  R3 = Rear TargetIO - Line 3
		  R4 = Rear TargetIO - Line 4
		  MM = Mode to combine multiple channels
		    00 = OR
			 01 = AND
						
	  0xXX - Trigger Module Enabled
	  
	   [ X  X  X  FB FA M  M  M ]
		  M M M = 000 Normal Edge-Mode Trigger
		          001 Advanced IO Pattern Trigger
					 010 Advanced SAD Trigger						
					 
		  FA = Output trigger to Front Panel A
		  FB = Output trigger to Front Panel B
		  
	  0xXX - GPIO Pin Routing [8 bytes]
	   
		IMPORTANT: Only a single IO can be assigned
		           to any input. e.g. you can't assign
					  both GPIO1 and GPIO3 to 'RX'. 
					  
					  The system assigns priority to lower
					  numbered GPIOs.
					  
					  Similarly if you attempt to assign multiple
					  outputs to a single TargetIO it will use the
					  lowest bit as the actual output.
		
		GPIO1:
		  [ E G   X     X  USII USIO RX TX ]
		  
		GPIO2:
		  [ E G   X     X  USII USIO RX TX ]
		  
		GPIO3:
		  [ E G   X  USOC  USII USIO RX TX ]  --> USOC means USIO but with Open Collector drive
		  
		RESERVED:
		  [ X X   X     X    X    X  X   X ]
		 
	   RESERVED:
		  [ X X   X     X    X    X  X   X ]
		
		RESERVED:
		  [ X X   X     X    X    X  X   X ]
		  
		RESERVED:
		  [ X X   X     X    X    X  X   X ]
		  
		RESERVED:
		  [ X X   X     X    X    X  X   X ]
 */
    
	 reg [7:0] registers_cwextclk;
	 reg [7:0] registers_cwtrigsrc;
	 reg [7:0] registers_cwtrigmod;
	 reg [63:0] registers_iorouting;
  	 
	
	 //Do to no assumed phase relationship we use regular old fabric for switching
	 assign extclk_o =   (registers_cwextclk[2:0] == 3'b000) ? extclk_fpa_io : 
							  (registers_cwextclk[2:0] == 3'b001) ? extclk_fpb_i : 
							  (registers_cwextclk[2:0] == 3'b010) ? extclk_pll_i : 
							  (registers_cwextclk[2:0] == 3'b011) ? extclk_rearin_i : 
							  //(registers_cwextclk[2:0] == 3'b100) ? extclk_rearout_o : 
							  1'b0;
							  
	 //TODO: Should use a mux?
	 //The glitch-clock comes from the fabric anyway, but the clkgen comes from the DCM. Either way we are jumping back
	 //and forth a lot.
	 //assign extclk_fpa_io = (registers_cwextclk[4:3] == 2'b01) ? clkgen_i :
	 //							  (registers_cwextclk[4:3] == 2'b10) ? glitchclk_i :
	 //							  1'bZ;
	 
	 assign extclk_fpa_io = 1'bZ;
	 
	
	wire rearclk;
	
	BUFGMUX #(
	.CLK_SEL_TYPE("ASYNC") // Glitchles ("SYNC") or fast ("ASYNC") clock switch-over
	)
	clkgenfx_mux (
	.O(rearclk), // 1-bit output: Clock buffer output
	.I0(clkgen_i), // 1-bit input: Clock buffer input (S=0)
	.I1(glitchclk_i), // 1-bit input: Clock buffer input (S=1)
	.S(registers_cwextclk[5]) // 1-bit input: Clock buffer select
	);
	
	//NB: Normally ODDR2 used for clock output. This won't work as this clock
	//can have glitches, which screws up the ODDR2 block. Because we don't care
	//about variations in synchronization of this clock to source clock, this
	//should be OK.
	/*
	ODDR2 #(
		// The following parameters specify the behavior
		// of the component.
		.DDR_ALIGNMENT("NONE"), // Sets output alignment
										// to "NONE", "C0" or "C1"
		.INIT(1'b0),    // Sets initial state of the Q 
							 //   output to 1'b0 or 1'b1
		.SRTYPE("ASYNC") // Specifies "SYNC" or "ASYNC"
							 //   set/reset
	)
	ODDR2_rearclk (
		.Q(extclk_rearout_o),   // 1-bit DDR output data
		.C0(rearclk), // 1-bit clock input
		.C1(~rearclk), // 1-bit clock input
		.CE(registers_cwextclk[6]), // 1-bit clock enable input
		.D0(1'b1), // 1-bit data input (associated with C0)
		.D1(1'b0), // 1-bit data input (associated with C1)
		.R(~registers_cwextclk[6]),   // 1-bit reset input
		.S(1'b0)    // 1-bit set input
	);
	*/
	assign extclk_rearout_o = registers_cwextclk[6] ? rearclk : 1'bZ;
	
	//Output clock using DDR2 block (recommended for Spartan-6 device)
	ODDR2 #(
		// The following parameters specify the behavior
		// of the component.
		.DDR_ALIGNMENT("NONE"), // Sets output alignment
										// to "NONE", "C0" or "C1"
		.INIT(1'b0),    // Sets initial state of the Q 
							 //   output to 1'b0 or 1'b1
		.SRTYPE("ASYNC") // Specifies "SYNC" or "ASYNC"
							 //   set/reset
	)
	ODDR2_hsglitch (
		.Q(hsglitch_o),   // 1-bit DDR output data
		.C0(glitchclk_i), // 1-bit clock input
		.C1(~glitchclk_i), // 1-bit clock input
		.CE(registers_cwextclk[7]), // 1-bit clock enable input
		.D0(1'b1), // 1-bit data input (associated with C0)
		.D1(1'b0), // 1-bit data input (associated with C1)
		.R(~registers_cwextclk[7]),   // 1-bit reset input
		.S(1'b0)    // 1-bit set input
	);
	
	
	 //TODO: Should use a mux?
	 /*
	 assign extclk_rearout_o = (registers_cwextclk[6:5] == 2'b01) ? clkgen_i :
								  (registers_cwextclk[6:5] == 2'b10) ? glitchclk_i :
								  1'bZ;	
	 */
		
	 wire trigger_and;
	 wire trigger_or;
	 wire trigger_ext;
	 
	 wire trigger_fpa;
	 
	 assign trigger_and = ((registers_cwtrigsrc[0] & trigger_fpa) | ~registers_cwtrigsrc[0]) &
								 ((registers_cwtrigsrc[1] & trigger_fpb_i) | ~registers_cwtrigsrc[1]) &
								 ((registers_cwtrigsrc[2] & trigger_io1_i) | ~registers_cwtrigsrc[2]) &
								 ((registers_cwtrigsrc[3] & trigger_io2_i) | ~registers_cwtrigsrc[3]) &
								 ((registers_cwtrigsrc[4] & trigger_io3_i) | ~registers_cwtrigsrc[4]) &
								 ((registers_cwtrigsrc[5] & trigger_io4_i) | ~registers_cwtrigsrc[5]);
								 
	 assign trigger_or  = (registers_cwtrigsrc[0] & trigger_fpa) |
								 (registers_cwtrigsrc[1] & trigger_fpb_i) |
								 (registers_cwtrigsrc[2] & trigger_io1_i) |
								 (registers_cwtrigsrc[3] & trigger_io2_i) |
								 (registers_cwtrigsrc[4] & trigger_io3_i) |
								 (registers_cwtrigsrc[5] & trigger_io4_i);	
								 
	 assign trigger_ext =  (registers_cwtrigsrc[7:6] == 2'b00) ? trigger_or :
								  (registers_cwtrigsrc[7:6] == 2'b01) ? trigger_and : 1'b0;
	
	 wire trigger;	 		  
	 assign trigger = (registers_cwtrigmod[2:0] == 3'b000) ? trigger_ext :
						   (registers_cwtrigmod[2:0] == 3'b001) ? trigger_advio_i : 
							(registers_cwtrigmod[2:0] == 3'b010) ? trigger_anapattern_i : 1'b0;
							
	 assign trigger_ext_o = trigger_ext;
	 
	 assign trigger_o = trigger;
	 
	 assign trigger_fpa_i =  (registers_cwtrigmod[3] == 1'b1) ? trigger : 1'bZ;
	 assign trigger_fpb_i =  (registers_cwtrigmod[4] == 1'b1) ? trigger : 1'bZ;	 
	 
	 
`ifndef DISABLE_FPA_IN
   IODELAY2 #(
			.COUNTER_WRAPAROUND("WRAPAROUND"), // "STAY_AT_LIMIT" or "WRAPAROUND"
			.DATA_RATE("SDR"), // "SDR" or "DDR"
			.DELAY_SRC("IDATAIN"), // "IO", "ODATAIN" or "IDATAIN"
			.IDELAY2_VALUE(0), // Delay value when IDELAY_MODE="PCI" (0-255)
			.IDELAY_MODE("NORMAL"), // "NORMAL" or "PCI"
			.IDELAY_TYPE("DEFAULT"), // "FIXED", "DEFAULT", "VARIABLE_FROM_ZERO", "VARIABLE_FROM_HALF_MAX"
			.IDELAY_VALUE(20), // Amount of taps for fixed input delay (0-255)
			.ODELAY_VALUE(0), // Amount of taps fixed output delay (0-255)
			.SERDES_MODE("NONE"), // "NONE", "MASTER" or "SLAVE"
			.SIM_TAPDELAY_VALUE(75) // Per tap delay used for simulation in ps
			)
		IODELAY2_inst (
			.BUSY(), // 1-bit output: Busy output after CAL
			.DATAOUT(), // 1-bit output: Delayed data output to ISERDES/input register
			.DATAOUT2(trigger_fpa), // 1-bit output: Delayed data output to general FPGA fabric
			.DOUT(), // 1-bit output: Delayed data output
			.TOUT(), // 1-bit output: Delayed 3-state output
			.CAL(~reset_i), // 1-bit input: Initiate calibration input
			.CE(1'b0), // 1-bit input: Enable INC input
			.CLK(), // 1-bit input: Clock input
			.IDATAIN(trigger_fpa_i), // 1-bit input: Data input (connect to top-level port or I/O buffer)
			.INC(), // 1-bit input: Increment / decrement input
			.IOCLK0(adc_sample_clk), // 1-bit input: Input from the I/O clock network
			.IOCLK1(), // 1-bit input: Input from the I/O clock network
			.ODATAIN(), // 1-bit input: Output data input from output register or OSERDES2.
			.RST(reset_i), // 1-bit input: Reset to zero or 1/2 of total delay period
			.T() // 1-bit input: 3-state input signal
		);
`endif
	 
	 /* IO Routing */
	 
	 assign targetio1_io = registers_iorouting[0 + 0] ? uart_tx_i :
								  registers_iorouting[0 + 2] ? usi_out_i :
								  registers_iorouting[0 + 7] ? registers_iorouting[0 + 6] :
								  1'bZ;
		
	 assign targetio2_io = registers_iorouting[8 + 0] ? uart_tx_i :
								  registers_iorouting[8 + 2] ? usi_out_i :
								  registers_iorouting[8 + 7] ? registers_iorouting[8 + 6] :
								  1'bZ;
								  
	 assign targetio3_io = registers_iorouting[16 + 0] ? uart_tx_i :
								  registers_iorouting[16 + 2] ? usi_out_i :
								  registers_iorouting[16 + 4] ? (usi_out_i ? 1'bZ : 1'b0) :
								  registers_iorouting[16 + 7] ? registers_iorouting[16 + 6] :
								  1'bZ;
								  
	 assign targetio4_io = 1'bZ;
	 
	 assign uart_rx_o = registers_iorouting[0 + 1] ? targetio1_io :
							registers_iorouting[8 + 1] ? targetio2_io :
							registers_iorouting[16 + 1] ? targetio3_io :
							1'b1;
							
	assign usi_in_o = registers_iorouting[0 + 3] ? targetio1_io :
							registers_iorouting[8 + 3] ? targetio2_io :
							registers_iorouting[16 + 3] ? targetio3_io :
							1'b1;	 
	 
	 reg [15:0] reg_hyplen_reg;
	 assign reg_hyplen = reg_hyplen_reg;
	 
	 always @(reg_hypaddress) begin
		case (reg_hypaddress)
            `CW_EXTCLK_ADDR: reg_hyplen_reg <= 1;
				`CW_TRIGSRC_ADDR: reg_hyplen_reg <= 1;
				`CW_TRIGMOD_ADDR: reg_hyplen_reg <= 1;
				`CW_IOROUTE_ADDR: reg_hyplen_reg <= 8;
				default: reg_hyplen_reg<= 0;
		endcase
	 end

	 reg [7:0] reg_datao_reg;
	 reg reg_datao_valid_reg;
	 assign reg_datao = (reg_datao_valid_reg/*& reg_read*/) ? reg_datao_reg : 8'd0;

	 always @(posedge clk) begin
		if (reg_addrvalid) begin
			case (reg_address)
				`CW_EXTCLK_ADDR: begin reg_datao_valid_reg <= 1; end
				`CW_TRIGSRC_ADDR: begin reg_datao_valid_reg <= 1; end
				`CW_TRIGMOD_ADDR: begin reg_datao_valid_reg <= 1; end
				`CW_IOROUTE_ADDR: begin reg_datao_valid_reg <= 1; end
				default: begin reg_datao_valid_reg <= 0; end	
			endcase
		end else begin
			reg_datao_valid_reg <= 0;
		end
	 end
	 
	 always @(posedge clk) begin
		if (reg_read) begin
			case (reg_address)
				`CW_EXTCLK_ADDR: reg_datao_reg <= registers_cwextclk; 
				`CW_TRIGSRC_ADDR: reg_datao_reg <= registers_cwtrigsrc; 
				`CW_TRIGMOD_ADDR: reg_datao_reg <= registers_cwtrigmod; 
				`CW_IOROUTE_ADDR: reg_datao_reg <= registers_iorouting[reg_bytecnt*8 +: 8];
				default: reg_datao_reg <= 0;	
			endcase
		end
	 end	  

	 always @(posedge clk) begin
		if (reset) begin
			registers_cwextclk <= 0;
			registers_cwtrigsrc <= 1;
			registers_cwtrigmod <= 0;
			registers_iorouting <= 64'b00000010_00000001;
		end else if (reg_write) begin
			case (reg_address)
				`CW_EXTCLK_ADDR: registers_cwextclk <= reg_datai;
				`CW_TRIGSRC_ADDR: registers_cwtrigsrc <= reg_datai;
				`CW_TRIGMOD_ADDR: registers_cwtrigmod <= reg_datai;
				`CW_IOROUTE_ADDR: registers_iorouting[reg_bytecnt*8 +: 8] <= reg_datai;
				default: ;
			endcase
		end
	 end	 

			
 `ifdef CHIPSCOPE
	 assign cs_data[5:0] = reg_address;
	 assign cs_data[21:6] = reg_bytecnt;
	 assign cs_data[29:22] = reg_datai;
	 assign cs_data[37:30] = reg_datao;
	 assign cs_data[38] = reg_read;
	 assign cs_data[39] = reg_write;
	 assign cs_data[40] = reg_addrvalid;
	 assign cs_data[46:41] = reg_hypaddress;
	 assign cs_data[62:47] = reg_hyplen;
 `endif
 
endmodule

`undef CHIPSCOPE
