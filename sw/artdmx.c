#include "artdmx.h"
#include <console.h>
#include <irq.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
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
    case 0x07:
      break;
    case '\r':
    case '\n':
      s[ptr] = 0x00;
      ptr = 0;
      return s;
    default:
      if (ptr >= (sizeof(s) - 1))
        break;
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

void nonechowrite(void) {
  while (1) {
    char *str;
    char *token;

    str = readstr();
    while (str == NULL) {
      str = readstr();
    }
    token = get_token(&str);
    if (strcmp(token, "write") == 0) {
      char *endptr;
      uint32_t adr = strtol(get_token(&str), &endptr, 16);
      uint32_t dat = strtol(get_token(&str), &endptr, 16);
      volatile uint32_t *ptr = (volatile uint32_t *)adr;
      *ptr = dat;
      flush_l2_cache();
    } else {
      puts("String:");
      puts(str);
      puts("done");
      return;
    }
  }
}
