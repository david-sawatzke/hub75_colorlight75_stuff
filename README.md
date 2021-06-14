# Setup

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
$ ./colorlite.py --revision 6.1 --build
$ ./colorlite.py --revision 6.1 --load
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
