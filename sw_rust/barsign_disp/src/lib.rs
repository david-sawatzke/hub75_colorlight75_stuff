#![no_std]

pub mod artnet;
pub mod ethernet;
pub mod hal;
pub mod hub75;
pub mod img;
pub mod img_flash;
pub mod menu;
pub mod panic;
pub mod pearson_hash;

// Returns mac in 6 byte octets and u64 where only the first 48 bits are set
pub fn generate_mac(uniq_data: &[u8]) -> ([u8; 6], u64) {
    let mut mac = [0; 6];

    // Generate mac from unique data, hash it to generate a nice "random" value
    pearson_hash::hash(uniq_data, &mut mac);
    // Disable multicast
    mac[0] &= !0b1;
    // Set locally administered addresses bit
    mac[0] |= 0b10;

    let mut mac_be: u64 = 0;
    for byte in mac {
        mac_be = (mac_be << 8) | byte as u64;
    }
    (mac, mac_be)
}
