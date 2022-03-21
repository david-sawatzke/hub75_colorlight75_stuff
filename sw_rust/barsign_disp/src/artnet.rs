use core::convert::TryInto;

pub fn packet2hub75(data: &[u8]) -> Result<(usize, impl Iterator<Item = u32> + '_), ()> {
    // if !data.starts_with(b"Art-net\0") {
    //     // Invalid Header
    //     Err(())?
    // }
    if data.len() < 18 {
        // Too short
        return Err(());
    }
    // if data[8] != 0 || data[9] != 0x50 {
    //     // Invalid command
    //     Err(())?
    // }
    // if data[8] != 0 || data[9] != 0x50 {
    //     // Invalid version
    //     Err(())?
    // }
    let universe = u16::from_le_bytes(data[14..16].try_into().unwrap());
    let length = u16::from_be_bytes(data[16..18].try_into().unwrap());
    // if length > 510 || data.len() > (510 + 18) {
    //     // Too long
    //     Err(())?
    // }
    if data.len() < (18 + (length as usize)) {
        // Too short
        return Err(());
    }
    let iter = data[18..length as usize + 18].chunks(3).map(|x: &[u8]| {
        let data = [x[0], x[1], x[2], 0];
        u32::from_le_bytes(data)
    });

    Ok((universe as usize * 170, iter))
}
