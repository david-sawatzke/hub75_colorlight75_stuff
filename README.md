# Setup
## Dependencies
- yosys
- trellis
- ecpprog
- python
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
