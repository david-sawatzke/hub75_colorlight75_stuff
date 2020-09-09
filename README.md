# Setup

## Install litex

(first create a venv)
``` sh
$ wget https://raw.githubusercontent.com/enjoy-digital/litex/master/litex_setup.py
$ chmod +x litex_setup.py
$ sudo ./litex_setup.py init install
```


## To build

``` sh
$ ./colorlite.py --revision 6.1 --build
$ ./colorlite.py --revision 6.1 --load
```
