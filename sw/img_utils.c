#include "img_utils.h"
#include "img_indexed.h"
#include <generated/csr.h>
#include <generated/mem.h>
#include <stdint.h>
#include <system.h>

void init_img_from_header(void) {
  volatile uint32_t *sdram_img_base =
      (volatile uint32_t *)(MAIN_RAM_BASE + (MAIN_RAM_SIZE / 2));
  for (uint32_t i = 0; i < img_data_len; i++) {
    // The byteorder is weird TODO fix in gateware
    *(sdram_img_base + i) = img_data[i ^ 0b11];
  }

  // Next up, init the palette
  volatile uint32_t *palette_base = (volatile uint32_t *)CSR_HUB75_PALETTE_BASE;
  for (uint32_t i = 0; i < palette_data_len; i++) {
    *(palette_base + i) = palette_data[i];
  }

  flush_l2_cache();
}
