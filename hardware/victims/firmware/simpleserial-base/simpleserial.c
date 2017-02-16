// simpleserial.c

#include "simpleserial.h"
#include <stdint.h>
#include "hal.h"

typedef struct ss_cmd
{
	char c;
	unsigned int len;
	void (*fp)(uint8_t*);
} ss_cmd;

#define MAX_SS_CMDS 10
ss_cmd commands[MAX_SS_CMDS];
static int num_commands = 0;

#define MAX_SS_LEN 64

static char hex_lookup[16] =
{
	'0', '1', '2', '3', '4', '5', '6', '7',
	'8', '9', 'A', 'B', 'C', 'D', 'E', 'F'
};

int hex_decode(int len, char* ascii_buf, char* data_buf)
{
	for(int i = 0; i < len; i++)
	{
		char n_hi = ascii_buf[2*i];
		char n_lo = ascii_buf[2*i+1];

		if(n_hi >= '0' && n_hi <= '9')
			data_buf[i] = n_hi - '0';
		else if(n_hi >= 'A' && n_hi <= 'F')
			data_buf[i] = n_hi - 'A' + 10;
		else if(n_hi >= 'a' && n_hi <= 'f')
			data_buf[i] = n_hi - 'a' + 10;
		else
			return 1;

		if(n_lo >= '0' && n_lo <= '9')
			data_buf[i] |= (n_lo - '0') << 4;
		else if(n_lo >= 'A' && n_lo <= 'F')
			data_buf[i] |= (n_lo - 'A' + 10) << 4;
		else if(n_lo >= 'a' && n_lo <= 'f')
			data_buf[i] |= (n_lo - 'a' + 10) << 4;
		else
			return 1;
	}

	return 0;
}

int simpleserial_addcmd(char c, unsigned int len, void (*fp)(uint8_t*))
{
	if(num_commands > MAX_SS_CMDS)
		return 1;

	if(len > MAX_SS_LEN)
		return 1;

	commands[num_commands].c   = c;
	commands[num_commands].len = len;
	commands[num_commands].fp  = fp;
	num_commands++;

	return 0;
}

void simpleserial_get(void)
{
	char ascii_buf[2*MAX_SS_LEN];
	char data_buf[MAX_SS_LEN];

	// Step 1: find which command we're receiving
	char c;
	c = getch();

	int cmd;
	for(cmd = 0; cmd < num_commands; cmd++)
	{
		if(commands[cmd].c == c)
			break;
	}

	if(cmd == num_commands)
		return;

	// Step 2: receive characters until we fill the ASCII buffer
	for(int i = 0; i < 2*commands[cmd].len; i++)
	{
		c = getch();

		// Check for early \n
		if(c == '\n' || c == '\r')
			return;
		
		// Check for characters out of bounds
		if(!((c >= '0' && c <= '9') || (c >= 'A' && c <= 'F')))
			return;

		ascii_buf[i] = c;
	}

	// Step 3: assert that last character is \n or \r
	c = getch();
	if(c != '\n' && c != '\r')
		return;

	// ASCII buffer is full: convert to bytes and run callback
	if(hex_decode(commands[cmd].len, ascii_buf, data_buf))
		return;

	commands[cmd].fp(data_buf);
}

void simpleserial_put(char c, int size, uint8_t* output)
{
	putch(c);
	for(int i = 0; i < size; i++)
	{
		putch(hex_lookup[output[i] >> 4 ]);
		putch(hex_lookup[output[i] & 0xF]);
	}
	putch('\n');
}
