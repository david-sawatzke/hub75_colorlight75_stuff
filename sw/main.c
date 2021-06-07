#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "img_utils.h"
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
  puts("write [adr] [dat]               - write data");
}

static void reboot(void) { ctrl_reset_write(1); }

static void display(void) {
  volatile uint32_t *palette0 = (volatile uint32_t *)0x90000000;

  if (*palette0 == 0) {
    *palette0 = 0xFF0088;
  } else {
    *palette0 = 0x000000;
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
  else if (strcmp(token, "write") == 0) {
    char *endptr;
    uint32_t adr = strtol(get_token(&str), &endptr, 16);
    uint32_t dat = strtol(get_token(&str), &endptr, 16);
    volatile uint32_t *ptr = (volatile uint32_t *)adr;
    *ptr = dat;
    flush_l2_cache();
  }
  prompt();
}

int main(void) {
#ifdef CONFIG_CPU_HAS_INTERRUPT
  irq_setmask(0);
  irq_setie(1);
#endif
  init_img_from_header();
  uart_init();

  puts("\nLab004 - CPU testing software built "__DATE__
       " "__TIME__
       "\n");
  help();
  prompt();

  while (1) {
    console_service();
  }

  return 0;
}
