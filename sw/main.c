#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "artdmx.h"
#include "img_utils.h"
#include "spi.h"
#include <console.h>
#include <generated/csr.h>
#include <irq.h>
#include <system.h>
#include <uart.h>

static char *readstr(void) {
  char c[2];
  static char s[64];
  static int ptr = 0;

  if (readchar_nonblock()) {
    c[0] = readchar();
    c[1] = 0;
    switch (c[0]) {
    case 0x7f:
    case 0x08:
      if (ptr > 0) {
        ptr--;
        putsnonl("\x08 \x08");
      }
      break;
    case 0x07:
      break;
    case '\r':
    case '\n':
      s[ptr] = 0x00;
      putsnonl("\n");
      ptr = 0;
      return s;
    default:
      if (ptr >= (sizeof(s) - 1))
        break;
      putsnonl(c);
      s[ptr] = c[0];
      ptr++;
      break;
    }
  }

  return NULL;
}

static char *get_token(char **str) {
  char *c, *d;

  c = (char *)strchr(*str, ' ');
  if (c == NULL) {
    d = *str;
    *str = *str + strlen(*str);
    return d;
  }
  *c = 0;
  d = *str;
  *str = c + 1;
  return d;
}

static void prompt(void) { printf("RUNTIME>"); }

static void help(void) {
  puts("Available commands:");
  puts("help                            - this command");
  puts("reboot                          - reboot CPU");
  puts("display                         - display test");
  puts("link                            - get link status");
  puts("load                            - load normal image");
  puts("load_spi                        - load spi image");
  puts("load_indexed                    - load indexed image");
  puts("on                              - turn display on");
  puts("off                             - turn display off");
  puts("write [adr] [dat]               - write data");
  puts("save_image_spi                  - write sdram image to spi");
  puts("read [adr]                      - read data");
  puts("read_spi [adr]                  - read spi data");
}

static void reboot(void) { ctrl_reset_write(1); }

static void display(void) {
  volatile uint32_t *palette0 = (volatile uint32_t *)CSR_HUB75_PALETTE_BASE;

  if (*palette0 == 0) {
    *palette0 = 0xFF0088;
  } else {
    *palette0 = 0x000000;
  }
}
static void link_status(void) {
  if (ethphy_rx_inband_status_link_status_read()) {
    puts("Link up");
  } else {
    puts("Link down");
  }
}

static void console_service(void) {
  char *str;
  char *token;

  str = readstr();
  if (str == NULL)
    return;
  token = get_token(&str);
  if (strcmp(token, "help") == 0)
    help();
  else if (strcmp(token, "reboot") == 0)
    reboot();
  else if (strcmp(token, "display") == 0)
    display();
  else if (strcmp(token, "link") == 0)
    link_status();
  else if (strcmp(token, "on") == 0)
    hub75_ctrl_enabled_write(1);
  else if (strcmp(token, "off") == 0)
    hub75_ctrl_enabled_write(0);
  else if (strcmp(token, "load") == 0)
    init_img_from_header();
  else if (strcmp(token, "load_spi") == 0)
    init_img_from_spi();
  else if (strcmp(token, "load_indexed") == 0)
    init_img_indexed_from_header();
  else if (strcmp(token, "save_image_spi") == 0)
    spi_program_image(64 * 32 * 4);
  else if (strcmp(token, "hidden_nonechowrite") == 0)
    nonechowrite();
  else if (strcmp(token, "write") == 0) {
    char *endptr;
    uint32_t adr = strtol(get_token(&str), &endptr, 16);
    uint32_t dat = strtol(get_token(&str), &endptr, 16);
    volatile uint32_t *ptr = (volatile uint32_t *)adr;
    *ptr = dat;
    flush_l2_cache();
  } else if (strcmp(token, "read") == 0) {
    char *endptr;
    uint32_t adr = strtol(get_token(&str), &endptr, 16);
    volatile uint32_t *ptr = (volatile uint32_t *)adr;
    uint32_t dat = *ptr;
    printf("0x%x\n", dat);
  } else if (strcmp(token, "read_spi") == 0) {
    char *endptr;
    uint32_t adr = strtol(get_token(&str), &endptr, 16);
    uint32_t dat = spi_read_byte(adr);
    printf("0x%x: 0x%x\n", adr, dat);
  } else {
    puts("Command not available!");
  }
  prompt();
}

int main(void) {
#ifdef CONFIG_CPU_HAS_INTERRUPT
  irq_setmask(0);
  irq_setie(1);
#endif
  spi_init();
  uart_init();
  puts("\nColorlight - Software built "__DATE__
       " "__TIME__
       "\n");

  help();
  prompt();

  while (1) {
    console_service();
  }

  return 0;
}
