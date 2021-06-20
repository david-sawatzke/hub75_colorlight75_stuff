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
$ python3 -m litex.soc.software.mkmscimg sw/firmware.bin -f --little -o sw/firmware.fbi
$ ecpprog -o 1M sw/firmware.fbi

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
## Pitfalls I ran into
1. `and` is silently dropped, maybe use `&` instead
