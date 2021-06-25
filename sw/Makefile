ifdef SIM
BUILD_DIR=../build/sim/
all: firmware_sim.bin
else
BUILD_DIR=../build/colorlight_5a_75b/
all: firmware.bin
endif

include $(BUILD_DIR)/software/include/generated/variables.mak
include $(SOC_DIRECTORY)/software/common.mak

OBJECTS=isr.o main.o img_utils.o img_data.o spi.o

LDFLAGS := $(LDFLAGS) --gc-sections


# pull in dependency info for *existing* .o files
-include $(OBJECTS:.o=.d)

%.bin: %.elf
	$(OBJCOPY) -O binary $< $@
	chmod -x $@

%.elf: $(OBJECTS)
	$(LD) $(LDFLAGS) \
		-T linker.ld \
		-N -o $@ \
		 $(BUILD_DIR)/software/libbase/crt0.o \
		$(OBJECTS) \
		-L$(BUILD_DIR)/software/libbase \
		-L$(BUILD_DIR)/software/libcompiler_rt \
		-lbase-nofloat -lcompiler_rt
	chmod -x $@

main.o: main.c
	$(compile)

%.o: %.c
	$(compile)

%.o: %.S
	$(assemble)

clean:
	$(RM) $(OBJECTS) $(OBJECTS:.o=.d) firmware.elf firmware.bin .*~ *~

.PHONY: all main.o clean load
