#![no_std]
#![no_main]

use core::fmt::Write as _;

use barsign_disp::*;
use embedded_hal::blocking::delay::DelayMs;
use embedded_hal::blocking::serial::Write;
use embedded_hal::serial::Read;
use ethernet::Eth;
use hal::*;
use heapless::Vec;
use litex_pac as pac;
use nb::block;
use riscv_rt::entry;
use smoltcp::iface::{EthernetInterfaceBuilder, NeighborCache};
use smoltcp::socket::{
    SocketSet, TcpSocket, TcpSocketBuffer, UdpPacketMetadata, UdpSocket, UdpSocketBuffer,
};
use smoltcp::time::{Duration, Instant};
use smoltcp::wire::{EthernetAddress, IpAddress, IpCidr};

#[entry]
fn main() -> ! {
    let peripherals = pac::Peripherals::take().unwrap();

    let mut serial = UART {
        registers: peripherals.UART,
    };

    serial.bwrite_all(b"Hello world!\n").unwrap();

    let hub75 = hub75::Hub75::new(peripherals.HUB75, peripherals.HUB75_PALETTE);
    let flash = img_flash::Flash::new(peripherals.SPIFLASH_MMAP);
    let mut delay = TIMER {
        registers: peripherals.TIMER0,
        sys_clk: 50_000_000,
    };
    let mut buffer = [0u8; 64];
    let out_data = heapless::Vec::new();
    let output = menu::Output { serial, out_data };
    let context = menu::Context {
        output,
        hub75,
        flash,
    };
    let mut r = menu::Runner::new(&menu::ROOT_MENU, &mut buffer, context);

    let device = Eth::new(peripherals.ETHMAC, peripherals.ETHMEM);
    let mut neighbor_cache_entries = [None; 8];
    let neighbor_cache = NeighborCache::new(&mut neighbor_cache_entries[..]);
    let mut ip_addrs = [IpCidr::new(IpAddress::v4(192, 168, 1, 50), 24)];
    let mut iface = EthernetInterfaceBuilder::new(device)
        .ethernet_addr(EthernetAddress::from_bytes(&[
            0xF6, 0x48, 0x74, 0xC8, 0xC4, 0x83,
        ]))
        .neighbor_cache(neighbor_cache)
        .ip_addrs(&mut ip_addrs[..])
        .finalize();

    let tcp_server_socket = {
        static mut TCP_SERVER_RX_DATA: [u8; 256] = [0; 256];
        static mut TCP_SERVER_TX_DATA: [u8; 256] = [0; 256];
        let tcp_rx_buffer = TcpSocketBuffer::new(unsafe { &mut TCP_SERVER_RX_DATA[..] });
        let tcp_tx_buffer = TcpSocketBuffer::new(unsafe { &mut TCP_SERVER_TX_DATA[..] });
        TcpSocket::new(tcp_rx_buffer, tcp_tx_buffer)
    };

    let udp_server_socket = {
        static mut UDP_SERVER_RX_DATA: [u8; 2048] = [0; 2048];
        static mut UDP_SERVER_TX_DATA: [u8; 2048] = [0; 2048];
        static mut UDP_SERVER_RX_METADATA: [UdpPacketMetadata; 32] = [UdpPacketMetadata::EMPTY; 32];
        static mut UDP_SERVER_TX_METADATA: [UdpPacketMetadata; 32] = [UdpPacketMetadata::EMPTY; 32];
        let udp_rx_buffer = unsafe {
            UdpSocketBuffer::new(&mut UDP_SERVER_RX_METADATA[..], &mut UDP_SERVER_RX_DATA[..])
        };
        let udp_tx_buffer = unsafe {
            UdpSocketBuffer::new(&mut UDP_SERVER_TX_METADATA[..], &mut UDP_SERVER_TX_DATA[..])
        };
        UdpSocket::new(udp_rx_buffer, udp_tx_buffer)
    };
    let mut sockets_entries: [_; 2] = Default::default();
    let mut sockets = SocketSet::new(&mut sockets_entries[..]);
    let tcp_server_handle = sockets.add(tcp_server_socket);
    let udp_server_handle = sockets.add(udp_server_socket);

    let mut time = Instant::from_millis(0);
    let mut telnet_active = false;
    loop {
        match iface.poll(&mut sockets, time) {
            Ok(_) => {}
            Err(_) => {}
        }

        // tcp:23: telnet for menu
        {
            let mut socket = sockets.get::<TcpSocket>(tcp_server_handle);
            if !socket.is_open() {
                if socket.listen(23).is_err() {
                    writeln!(r.context.output.serial, "Couldn't listen to telnet port");
                }
            }
            if !telnet_active & socket.is_active() {
                r.context.output.out_data.clear();
                r.context
                    .output
                    .out_data
                    .extend_from_slice(
                        // Taken from https://stackoverflow.com/a/4532395
                        // Does magic telnet stuff to behave more like a dumb serial terminal
                        b"\xFF\xFD\x22\xFF\xFA\x22\x01\x00\xFF\xF0\xFF\xFB\x01\r\nWelcome to the menu. Use \"help\" for help\r\n",
                    )
                    .expect("Should always work");
            }
            telnet_active = socket.is_active();

            if socket.may_recv() {
                while socket.can_recv() {
                    let mut buffer = [0u8; 64];
                    let received = {
                        match socket.recv_slice(&mut buffer) {
                            Ok(received) => received,
                            _ => 0,
                        }
                    };
                    for byte in &buffer[..received] {
                        if *byte != 0 {
                            r.input_byte(*byte);
                        }
                        // r.input_byte(if data == b'\n' { b'\r' } else { data });
                    }

                    // socket.send_slice(core::slice::from_ref(&data)).unwrap();
                }
            } else if socket.can_send() {
                socket.close();
            }

            if socket.can_send() {
                if let Ok(sent) = socket.send_slice(&r.context.output.out_data) {
                    let new_data = Vec::from_slice(&r.context.output.out_data[sent..])
                        .expect("New size is the same as the old size, can never fail");
                    r.context.output.out_data = new_data;
                }
            }
        }
        // udp:6454: artnet
        {
            let mut socket = sockets.get::<UdpSocket>(udp_server_handle);
            if !socket.is_open() {
                if !socket.bind(6454).is_ok() {
                    writeln!(r.context.output.serial, "Couldn't open artnet port");
                }
            }

            match socket.recv() {
                Ok((data, _endpoint)) => {
                    if let Ok((offset, data)) = artnet::packet2hub75(data) {
                        // Palette is set via the two *last* universes
                        let palette_offset = ((1 << 16) - 2) * 170;
                        if offset < palette_offset {
                            // r.context.hub75.write_img_data(offset, data);
                        } else {
                            r.context
                                .hub75
                                .set_palette((offset - palette_offset) as u8, data);
                        }
                        // writeln!(r.context.serial, "{}", offset);
                    }
                }
                Err(_) => (),
            };
            // if let Some(endpoint) = client {
            //     let data = b"Hello World!\r\n";
            //     socket.send_slice(data, endpoint).unwrap();
            // }
        }
        if let Ok(data) = r.context.output.serial.read() {
            r.input_byte(if data == b'\n' { b'\r' } else { data });
        }

        // match iface.poll_delay(&sockets, time) {
        //     Some(Duration { millis: 0 }) => {}
        //     Some(delay_duration) => {
        //         // delay.delay_ms(delay_duration.total_millis() as u32);
        //         time += delay_duration
        //     }
        //     None => time += Duration::from_millis(1),
        // }
        time += Duration::from_millis(1);
    }
}
