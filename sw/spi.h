#ifndef SPI_H_
#define SPI_H_

#include <stdint.h>

void spi_init(void);
uint8_t spi_read_byte(uint32_t adr);
void spi_program_image(uint32_t length);

#endif // SPI_H_
