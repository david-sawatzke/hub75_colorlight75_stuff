# Features
- IP Networking (static IP)
- Management console over telnet & serial
- FullColor & Indexed mode, both usable with Art-Net
  - Palette changeable via the last two universes
  - Only with mod 3 lengths
- Save & Load image via flash
- Change panel & image parameters via console and save/load them from flash


# Notes for new boards
The flash *may* have a write lock. Remove it with
`ecpprog -p`

I've done flashing using a FT2232 & ecpprog (integrated in the colorlight.py script). The JTAG pinout for the different board revisions is documented in the [chubb75 project](https://github.com/q3k/chubby75/)

# Setup
## Dependencies
- yosys
- trellis
- nextpnr
- ecpprog
- python
- pypng
- ...

## Install litex

(first create a venv)
``` sh
$ wget https://raw.githubusercontent.com/enjoy-digital/litex/master/litex_setup.py
$ chmod +x litex_setup.py
$ sudo ./litex_setup.py init install
```

## Install other dependencies

``` sh
pip install -r requirements.txt
```

## To build

``` sh
$ ./colorlight.py --revision 6.1 --build
```
## Load or flash
``` sh
$ ./colorlight.py --revision 6.1 --load
$ ./colorlight.py --revision 6.1 --flash
```
## Load sw

``` sh
$ lxterm /dev/ttyUSB1 --kernel sw/firmware.bin
```

## Flash sw

``` sh
$ python3 -m litex.soc.software.mkmscimg sw_rust/barsign_disp/target/riscv32i-unknown-none-elf/release/barsign-disp.bin -f --little -o firmware.fbi
$ ecpprog -o 1M firmware.fbi
```

## To simulate SoC
Compile software

``` sh
make SIM=X
```

Run it
``` sh
./litex_sim.py --sdram-init sw/firmware_sim.bin 
```

Ethernet port

``` sh
sudo ip tuntap add tap0 mode tap
sudo ip l  set dev tap0 up
```

## Serial Port

``` sh
$ picocom -b 115200 /dev/ttyUSB1 --imap lfcrlf
```

## Pitfalls I ran into
1. `and` is silently dropped, maybe use `&` instead

