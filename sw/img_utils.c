#include "img_data.h"
#include "img_utils.h"
#include <generated/csr.h>
#include <generated/mem.h>
#include <stdint.h>
#include <system.h>

void set_common_params(void);

void set_common_params(void) {
  hub75_panel0_y_write(0);
  hub75_panel1_y_write(1);
  hub75_panel2_y_write(1);
  hub75_panel3_y_write(0);
  hub75_ctrl_enabled_write(1);
  hub75_ctrl_width_write(64);
}

void init_img_indexed_from_header(void) {
  volatile uint32_t *sdram_img_base =
      (volatile uint32_t *)(MAIN_RAM_BASE + (MAIN_RAM_SIZE / 2));
  for (uint32_t i = 0; i < img_indexed_data_len; i++) {
    *(sdram_img_base + i) = img_indexed_data[i];
  }

  // Next up, init the palette
  volatile uint32_t *palette_base = (volatile uint32_t *)CSR_HUB75_PALETTE_BASE;
  for (uint32_t i = 0; i < palette_data_len; i++) {
    *(palette_base + i) = palette_data[i];
  }

  flush_l2_cache();

  // Enable indexed mode
  hub75_ctrl_indexed_write(1);
  set_common_params();
}

void init_img_from_header(void) {
  volatile uint32_t *sdram_img_base =
      (volatile uint32_t *)(MAIN_RAM_BASE + (MAIN_RAM_SIZE / 2));
  for (uint32_t i = 0; i < img_data_len; i++) {
    *(sdram_img_base + i) = img_data[i];
  }

  flush_l2_cache();

  // Disable indexed mode
  hub75_ctrl_indexed_write(0);
  set_common_params();
}
